<?php
declare(strict_types=1);

const SYSTEM_SESSION_ID_PATTERN = '/^[a-f0-9]{32}$/';
const SYSTEM_FRAME_ID_PATTERN = '/^[A-Za-z0-9_-]{1,96}$/';
const SYSTEM_SESSION_MAX_IMAGE_BYTES = 20 * 1024 * 1024;
const SYSTEM_SESSION_MAX_FRAMES = 500;

function apiJson(array $payload, int $status = 200): void
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function apiFail(string $message, int $status): void
{
    apiJson(['success' => false, 'error' => $message], $status);
}

function systemSessionsRoot(): string
{
    return dirname(__DIR__, 2) . DIRECTORY_SEPARATOR . 'data'
        . DIRECTORY_SEPARATOR . 'system-sessions';
}

function ensureSystemSessionsRoot(): string
{
    $root = systemSessionsRoot();
    if (!is_dir($root) && !mkdir($root, 0750, true) && !is_dir($root)) {
        apiFail('Nie można utworzyć katalogu sesji.', 500);
    }
    return $root;
}

function atomicJsonWrite(string $path, array $data): void
{
    $directory = dirname($path);
    if (!is_dir($directory) && !mkdir($directory, 0750, true) && !is_dir($directory)) {
        throw new RuntimeException('Nie można utworzyć katalogu danych.');
    }
    $encoded = json_encode(
        $data,
        JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR
    );
    $temporary = $path . '.' . bin2hex(random_bytes(6)) . '.tmp';
    $handle = fopen($temporary, 'xb');
    if ($handle === false) {
        throw new RuntimeException('Nie można utworzyć pliku tymczasowego.');
    }
    try {
        if (!flock($handle, LOCK_EX) || fwrite($handle, $encoded) !== strlen($encoded) || !fflush($handle)) {
            throw new RuntimeException('Nie można zapisać stanu sesji.');
        }
    } finally {
        fclose($handle);
    }
    if (!rename($temporary, $path)) {
        @unlink($temporary);
        throw new RuntimeException('Nie można zatwierdzić stanu sesji.');
    }
}

function readJsonFile(string $path): ?array
{
    if (!is_file($path)) {
        return null;
    }
    $contents = file_get_contents($path);
    if ($contents === false) {
        return null;
    }
    $decoded = json_decode($contents, true);
    return is_array($decoded) ? $decoded : null;
}

function readJsonRequest(): array
{
    $contents = file_get_contents('php://input');
    $decoded = $contents === false ? null : json_decode($contents, true);
    if (!is_array($decoded)) {
        apiFail('Żądanie musi zawierać obiekt JSON.', 400);
    }
    return $decoded;
}

function requireMethod(string $method): void
{
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== $method) {
        header('Allow: ' . $method);
        apiFail('Niedozwolona metoda HTTP.', 405);
    }
}

function validId($value, string $pattern): bool
{
    return is_string($value) && preg_match($pattern, $value) === 1;
}

function finiteNumber($value): bool
{
    return (is_int($value) || is_float($value)) && is_finite((float) $value);
}

function finiteVector($value, int $length, string $field, float $minimum, float $maximum): array
{
    if (!is_array($value) || count($value) !== $length) {
        apiFail("$field musi być tablicą $length liczb.", 400);
    }
    foreach ($value as $number) {
        if (!finiteNumber($number) || $number < $minimum || $number > $maximum) {
            apiFail("$field zawiera liczbę poza dozwolonym zakresem.", 400);
        }
    }
    return array_values($value);
}

function canonicalize($value)
{
    if (!is_array($value)) {
        return $value;
    }
    if (array_is_list($value)) {
        return array_map('canonicalize', $value);
    }
    ksort($value, SORT_STRING);
    foreach ($value as $key => $child) {
        $value[$key] = canonicalize($child);
    }
    return $value;
}

function canonicalJson(array $value): string
{
    return json_encode(canonicalize($value), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
}

function sameFrameContent(array $existing, string $actualHash, string $canonicalMetadata): bool
{
    return isset($existing['sha256'], $existing['metadataCanonical'])
        && is_string($existing['sha256'])
        && is_string($existing['metadataCanonical'])
        && hash_equals($existing['sha256'], $actualHash)
        && hash_equals($existing['metadataCanonical'], $canonicalMetadata);
}

function checkedSystemSession(string $id): array
{
    if (!validId($id, SYSTEM_SESSION_ID_PATTERN)) {
        apiFail('Nieprawidłowy systemSessionId.', 400);
    }
    $root = ensureSystemSessionsRoot();
    $directory = $root . DIRECTORY_SEPARATOR . $id;
    if (is_link($directory)) {
        apiFail('Nieprawidłowa ścieżka sesji.', 400);
    }
    $realRoot = realpath($root);
    $realDirectory = realpath($directory);
    if ($realRoot === false || $realDirectory === false
        ||         strpos($realDirectory, $realRoot . DIRECTORY_SEPARATOR) !== 0
        || basename($realDirectory) !== $id) {
        apiFail('Sesja systemowa nie istnieje.', 404);
    }
    $session = readJsonFile($realDirectory . DIRECTORY_SEPARATOR . 'session.json');
    if ($session === null) {
        apiFail('Sesja systemowa nie istnieje.', 404);
    }
    return [$realDirectory, $session];
}

function updateLease(string $root, string $deviceId, ?string $sessionId, ?string $expectedSessionId = null): void
{
    $leases = $root . DIRECTORY_SEPARATOR . 'leases';
    if (!is_dir($leases) && !mkdir($leases, 0750, true) && !is_dir($leases)) {
        throw new RuntimeException('Nie można utworzyć katalogu blokad.');
    }
    $path = $leases . DIRECTORY_SEPARATOR . hash('sha256', $deviceId) . '.json';
    $handle = fopen($path . '.lock', 'c+');
    if ($handle === false || !flock($handle, LOCK_EX)) {
        if (is_resource($handle)) {
            fclose($handle);
        }
        throw new RuntimeException('Nie można zablokować identyfikatora urządzenia.');
    }
    try {
        $lease = readJsonFile($path);
        if ($sessionId === null) {
            if ($expectedSessionId !== null
                && ($lease['systemSessionId'] ?? null) !== $expectedSessionId) {
                return;
            }
            if ($lease !== null && isset($lease['systemSessionId'])
                && validId($lease['systemSessionId'], SYSTEM_SESSION_ID_PATTERN)
                && is_file($root . '/' . $lease['systemSessionId'] . '/session.json')) {
                $current = readJsonFile($root . '/' . $lease['systemSessionId'] . '/session.json');
                if ($current !== null && ($current['deviceId'] ?? null) === $deviceId) {
                    $current['acceptingFrames'] = false;
                    $current['status'] = 'closing';
                    atomicJsonWrite($root . '/' . $lease['systemSessionId'] . '/session.json', $current);
                }
            }
            @unlink($path);
            return;
        }
        atomicJsonWrite($path, ['deviceId' => $deviceId, 'systemSessionId' => $sessionId]);
    } finally {
        flock($handle, LOCK_UN);
        fclose($handle);
    }
}

function validateFrameMetadata(array $metadata, int $actualWidth, int $actualHeight, string $actualMime): array
{
    if (array_key_exists('cameraToSystemSessionFrame', $metadata)) {
        apiFail('cameraToSystemSessionFrame jest niejednoznaczne; klient musi jawnie przesłać cameraToFirstFrame.', 400);
    }
    $required = [
        'frameId', 'sequence', 'timestampMs', 'trackingState', 'assetId', 'sha256', 'mimeType',
        'width', 'height', 'orientation', 'imageTransform', 'arSessionEpochId', 'referenceFrameId',
        'cameraToFirstFrame', 'intrinsics', 'distortionStatus', 'cameraProfile',
    ];
    foreach ($required as $field) {
        if (!array_key_exists($field, $metadata)) {
            apiFail("Brak wymaganego pola metadata.$field.", 400);
        }
    }
    foreach (array_keys($metadata) as $field) {
        if (!is_string($field)) {
            apiFail('Klucze metadata muszą być tekstowe.', 400);
        }
    }
    $reservedFields = [
        'systemSessionId', 'mogeToCameraMatrix4x4', 'scaleEstimate', 'axes',
        'metadataCanonical', 'imageFile', 'status', 'progress', 'attempts', 'createdAt',
    ];
    if (array_intersect(array_keys($metadata), $reservedFields) !== []) {
        apiFail('metadata zawiera pole zarezerwowane lub konwencję modelu; systemSessionId i konwencja MoGe nie pochodzą od klienta.', 400);
    }
    if (!validId($metadata['frameId'], SYSTEM_FRAME_ID_PATTERN)) {
        apiFail('Nieprawidłowy frameId.', 400);
    }
    foreach (['timestampMs', 'width', 'height'] as $field) {
        if (!is_int($metadata[$field]) || $metadata[$field] < 1) {
            apiFail("metadata.$field musi być dodatnią liczbą całkowitą.", 400);
        }
    }
    if ($metadata['width'] > 32768 || $metadata['height'] > 32768
        || $metadata['width'] * $metadata['height'] > 100000000) {
        apiFail('Wymiary obrazu przekraczają dozwolony zakres.', 413);
    }
    if (!is_int($metadata['sequence']) || $metadata['sequence'] < 0) {
        apiFail('metadata.sequence musi być nieujemną liczbą całkowitą.', 400);
    }
    if ($metadata['sequence'] > 2147483647 || $metadata['timestampMs'] > 9007199254740991) {
        apiFail('Numer sekwencji lub timestamp przekracza zakres.', 400);
    }
    foreach (['trackingState', 'assetId', 'arSessionEpochId', 'referenceFrameId'] as $field) {
        if (!is_string($metadata[$field]) || $metadata[$field] === '' || strlen($metadata[$field]) > 128) {
            apiFail("metadata.$field musi być tekstem o długości 1–128.", 400);
        }
    }
    if (!in_array($metadata['trackingState'], ['TRACKING', 'PAUSED', 'STOPPED', 'LIMITED'], true)) {
        apiFail('trackingState musi być TRACKING, PAUSED, STOPPED lub LIMITED.', 400);
    }
    if (!is_string($metadata['sha256']) || preg_match('/^[a-f0-9]{64}$/', $metadata['sha256']) !== 1) {
        apiFail('metadata.sha256 musi być SHA-256 w zapisie hex.', 400);
    }
    if (!is_string($metadata['mimeType']) || $metadata['mimeType'] !== $actualMime) {
        apiFail('MIME metadanych nie odpowiada zawartości obrazu.', 400);
    }
    if ($metadata['width'] !== $actualWidth || $metadata['height'] !== $actualHeight) {
        apiFail('Wymiary obrazu nie odpowiadają metadanym.', 400);
    }
    if (!in_array($metadata['orientation'], [0, 90, 180, 270], true)) {
        apiFail('orientation musi wynosić 0, 90, 180 lub 270 stopni.', 400);
    }
    $transform = $metadata['imageTransform'];
    if (!is_array($transform) || !isset($transform['sourceWidth'], $transform['sourceHeight'],
        $transform['rotationDegrees'], $transform['mirrorX'], $transform['crop'])
        || !is_int($transform['sourceWidth']) || $transform['sourceWidth'] < 1 || $transform['sourceWidth'] > 65536
        || !is_int($transform['sourceHeight']) || $transform['sourceHeight'] < 1 || $transform['sourceHeight'] > 65536
        || !in_array($transform['rotationDegrees'], [0, 90, 180, 270], true)
        || !is_bool($transform['mirrorX']) || !is_array($transform['crop'])) {
        apiFail('imageTransform musi jawnie opisywać źródło, crop, obrót i odbicie.', 400);
    }
    $crop = $transform['crop'];
    foreach (['x', 'y', 'width', 'height'] as $field) {
        if (!isset($crop[$field]) || !finiteNumber($crop[$field])) {
            apiFail("imageTransform.crop.$field musi być liczbą.", 400);
        }
    }
    if ($crop['x'] < 0 || $crop['y'] < 0 || $crop['width'] <= 0 || $crop['height'] <= 0
        || $crop['x'] + $crop['width'] > 1 || $crop['y'] + $crop['height'] > 1) {
        apiFail('imageTransform.crop musi mieścić się w znormalizowanym obrazie źródłowym.', 400);
    }

    $pose = $metadata['cameraToFirstFrame'];
    $poseKeys = is_array($pose) ? array_keys($pose) : [];
    sort($poseKeys, SORT_STRING);
    if (!is_array($pose) || $poseKeys !== ['rotationQuaternionXyzw', 'translationM']) {
        apiFail('Brak jawnego cameraToFirstFrame.translationM/rotationQuaternionXyzw.', 400);
    }
    finiteVector($pose['translationM'], 3, 'translationM', -1000000, 1000000);
    $quaternion = finiteVector($pose['rotationQuaternionXyzw'], 4, 'rotationQuaternionXyzw', -1.001, 1.001);
    $norm = sqrt(array_sum(array_map(static fn($v) => $v * $v, $quaternion)));
    if (abs($norm - 1.0) > 0.001) {
        apiFail('Quaternion xyzw musi być znormalizowany.', 400);
    }
    if ($metadata['sequence'] === 0
        && (max(array_map('abs', $pose['translationM'])) > 0.001
            || max(array_map('abs', array_slice($quaternion, 0, 3))) > 0.001
            || abs(abs($quaternion[3]) - 1.0) > 0.001)) {
        apiFail('Klatka sequence=0 musi mieć tożsamościowy cameraToFirstFrame.', 400);
    }
    $intrinsics = $metadata['intrinsics'];
    if (!is_array($intrinsics)) {
        apiFail('intrinsics musi być obiektem.', 400);
    }
    foreach (['fx', 'fy', 'cx', 'cy'] as $field) {
        if (!isset($intrinsics[$field]) || !finiteNumber($intrinsics[$field])) {
            apiFail("intrinsics.$field musi być skończoną liczbą.", 400);
        }
    }
    if ($intrinsics['fx'] <= 0 || $intrinsics['fy'] <= 0 || $intrinsics['cx'] < 0
        || $intrinsics['cx'] > $actualWidth || $intrinsics['cy'] < 0 || $intrinsics['cy'] > $actualHeight) {
        apiFail('Intrinsics są poza zakresem obrazu.', 400);
    }
    if ($metadata['distortionStatus'] !== 'not_provided') {
        apiFail('Obsługiwany jest wyłącznie distortionStatus=not_provided; brak danych nie oznacza zera.', 400);
    }
    if (!is_array($metadata['cameraProfile']) || $metadata['cameraProfile'] === []) {
        apiFail('cameraProfile musi być niepustym obiektem stabilnego profilu.', 400);
    }
    return $metadata;
}
