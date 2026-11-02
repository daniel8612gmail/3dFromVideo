<?php
declare(strict_types=1);
require __DIR__ . '/_common.php';
requireMethod('POST');

$id = $_GET['systemSessionId'] ?? ($_POST['systemSessionId'] ?? '');
[$directory, $session] = checkedSystemSession(is_string($id) ? $id : '');
if (!isset($_FILES['photo']) || !is_array($_FILES['photo'])) {
    apiFail('Wymagany jest multipart field photo.', 400);
}
$file = $_FILES['photo'];
if (($file['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK) {
    $uploadErrors = [
        UPLOAD_ERR_INI_SIZE => 'Plik przekracza limit serwera.',
        UPLOAD_ERR_FORM_SIZE => 'Plik przekracza limit formularza.',
        UPLOAD_ERR_PARTIAL => 'Plik został przesłany częściowo.',
        UPLOAD_ERR_NO_FILE => 'Nie przesłano zdjęcia.',
        UPLOAD_ERR_NO_TMP_DIR => 'Brak katalogu tymczasowego.',
        UPLOAD_ERR_CANT_WRITE => 'Nie można zapisać pliku.',
        UPLOAD_ERR_EXTENSION => 'Upload został przerwany przez PHP.',
    ];
    apiFail($uploadErrors[$file['error']] ?? 'Błąd uploadu.', 400);
}
if (($file['size'] ?? 0) < 1 || $file['size'] > SYSTEM_SESSION_MAX_IMAGE_BYTES) {
    apiFail('Zdjęcie musi mieć rozmiar 1–20 MiB.', 413);
}
if (!is_uploaded_file($file['tmp_name'])) {
    apiFail('Nieprawidłowy upload pliku.', 400);
}
$image = @getimagesize($file['tmp_name']);
$mime = is_array($image) ? ($image['mime'] ?? '') : '';
$extensions = ['image/jpeg' => 'jpg', 'image/png' => 'png', 'image/webp' => 'webp'];
if (!isset($extensions[$mime])) {
    apiFail('Dozwolone są wyłącznie JPEG, PNG i WebP.', 415);
}
$metadataJson = $_POST['metadata'] ?? null;
if (!is_string($metadataJson)) {
    apiFail('multipart field metadata musi zawierać obiekt JSON.', 400);
}
if (strlen($metadataJson) > 65536) {
    apiFail('metadata musi mieć maksymalnie 64 KiB.', 413);
}
$metadata = is_string($metadataJson) ? json_decode($metadataJson, true) : null;
if (!is_array($metadata)) {
    apiFail('multipart field metadata musi zawierać obiekt JSON.', 400);
}
$metadata = validateFrameMetadata($metadata, (int) $image[0], (int) $image[1], $mime);
$actualHash = hash_file('sha256', $file['tmp_name']);
if (!is_string($actualHash) || !hash_equals($metadata['sha256'], $actualHash)) {
    apiFail('SHA-256 zdjęcia nie odpowiada metadata.sha256.', 400);
}

$frameId = $metadata['frameId'];
$frameDir = $directory . DIRECTORY_SEPARATOR . 'frames' . DIRECTORY_SEPARATOR . $frameId;
if (is_link($frameDir)) {
    apiFail('Nieprawidłowa ścieżka klatki.', 400);
}
if (!is_dir($frameDir) && !mkdir($frameDir, 0750, true) && !is_dir($frameDir)) {
    apiFail('Nie można utworzyć katalogu klatki.', 500);
}
$lock = fopen($directory . DIRECTORY_SEPARATOR . 'session.lock', 'c+');
if ($lock === false || !flock($lock, LOCK_EX)) {
    if (is_resource($lock)) {
        fclose($lock);
    }
    apiFail('Nie można zablokować sesji.', 500);
}
try {
    $session = readJsonFile($directory . DIRECTORY_SEPARATOR . 'session.json');
    if ($session === null) {
        apiFail('Sesja systemowa nie istnieje.', 404);
    }
    $frameJsonPath = $frameDir . DIRECTORY_SEPARATOR . 'frame.json';
    $existing = readJsonFile($frameJsonPath);
    $canonicalMetadata = canonicalJson($metadata);
    if ($existing !== null) {
        if (sameFrameContent($existing, $actualHash, $canonicalMetadata)) {
            apiJson(['success' => true, 'systemSessionId' => $id, 'frameId' => $frameId,
                'status' => $existing['status'] ?? 'queued', 'progress' => $existing['progress'] ?? 0,
                'idempotent' => true], 200);
        }
        apiFail('frameId został już użyty z inną zawartością lub metadanymi.', 409);
    }
    if (($session['acceptingFrames'] ?? false) !== true) {
        apiFail('Sesja jest zamknięta i nie przyjmuje nowych klatek.', 409);
    }
    $currentStatus = readJsonFile($directory . DIRECTORY_SEPARATOR . 'status.json') ?? [];
    if (($currentStatus['status'] ?? '') === 'error') {
        apiFail('Sesja jest w stanie błędu; utwórz nową systemSessionId.', 409);
    }
    foreach (glob($directory . DIRECTORY_SEPARATOR . 'frames' . DIRECTORY_SEPARATOR . '*' . DIRECTORY_SEPARATOR . 'frame.json') ?: [] as $path) {
        $other = readJsonFile($path);
        if ($other === null) {
            continue;
        }
        if (($other['sequence'] ?? null) === $metadata['sequence']) {
            apiFail('sequence musi być unikalny w obrębie sesji.', 409);
        }
    }
    $existingFramePaths = glob($directory . DIRECTORY_SEPARATOR . 'frames' . DIRECTORY_SEPARATOR . '*' . DIRECTORY_SEPARATOR . 'frame.json') ?: [];
    if ($existingFramePaths === [] && $metadata['sequence'] !== 0) {
        apiFail('Pierwsza klatka logicznej sesji musi mieć sequence=0.', 409);
    }
    if (count($existingFramePaths) >= SYSTEM_SESSION_MAX_FRAMES) {
        apiFail('Osiągnięto limit klatek sesji.', 413);
    }
    $profile = canonicalJson($metadata['cameraProfile']);
    if ($session['cameraProfile'] !== null && $session['cameraProfile'] !== $profile) {
        apiFail('cameraProfile musi pozostać stabilny w obrębie sesji.', 409);
    }
    if (!move_uploaded_file($file['tmp_name'], $frameDir . DIRECTORY_SEPARATOR . 'image.' . $extensions[$mime])) {
        apiFail('Nie udało się zapisać zdjęcia.', 500);
    }
    $record = $metadata;
    $record['metadataCanonical'] = $canonicalMetadata;
    $record['sha256'] = $actualHash;
    $record['imageFile'] = 'image.' . $extensions[$mime];
    $record['status'] = 'queued';
    $record['progress'] = 0;
    $record['attempts'] = 0;
    $record['createdAt'] = (int) floor(microtime(true) * 1000);
    atomicJsonWrite($frameJsonPath, $record);
    $epochs = is_array($session['arSessionEpochs'] ?? null) ? $session['arSessionEpochs'] : [];
    if (!in_array($metadata['arSessionEpochId'], $epochs, true)) {
        $epochs[] = $metadata['arSessionEpochId'];
    }
    $session['arSessionEpochs'] = $epochs;
    $session['cameraProfile'] = $profile;
    $session['frameCount'] = count($existingFramePaths) + 1;
    $session['status'] = 'queued';
    atomicJsonWrite($directory . DIRECTORY_SEPARATOR . 'session.json', $session);
    $status = readJsonFile($directory . DIRECTORY_SEPARATOR . 'status.json') ?? [];
    $status['status'] = 'queued';
    $status['totalFrames'] = $session['frameCount'];
    atomicJsonWrite($directory . DIRECTORY_SEPARATOR . 'status.json', $status);
    apiJson(['success' => true, 'systemSessionId' => $id, 'frameId' => $frameId,
        'status' => 'queued', 'progress' => 0, 'idempotent' => false], 202);
} catch (Throwable $error) {
    apiFail('Nie udało się zapisać klatki.', 500);
} finally {
    flock($lock, LOCK_UN);
    fclose($lock);
}
