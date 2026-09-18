<?php

header('Content-Type: application/json; charset=utf-8');

/*
|--------------------------------------------------------------------------
| Funkcja odpowiedzi JSON
|--------------------------------------------------------------------------
*/

function sendJson(array $data, int $statusCode = 200): void
{
    http_response_code($statusCode);

    echo json_encode(
        $data,
        JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES
    );

    exit;
}

/*
|--------------------------------------------------------------------------
| Tylko POST
|--------------------------------------------------------------------------
*/

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    sendJson([
        'success' => false,
        'error' => 'Dozwolona jest tylko metoda POST.'
    ], 405);
}

/*
|--------------------------------------------------------------------------
| Session ID
|--------------------------------------------------------------------------
*/

$sessionId = $_GET['sessionId'] ?? '';

if (!preg_match('/^[a-f0-9]{32}$/', $sessionId)) {
    sendJson([
        'success' => false,
        'error' => 'Nieprawidłowy identyfikator sesji.'
    ], 400);
}

/*
|--------------------------------------------------------------------------
| Katalog danych
|--------------------------------------------------------------------------
*/

$dataDir = __DIR__ . '/data';

$sessionDir = $dataDir . '/' . $sessionId;

/*
|--------------------------------------------------------------------------
| Sprawdzenie sesji
|--------------------------------------------------------------------------
*/

if (!is_dir($sessionDir)) {
    sendJson([
        'success' => false,
        'error' => 'Sesja nie istnieje.'
    ], 404);
}

/*
|--------------------------------------------------------------------------
| Dodatkowa kontrola ścieżki
|--------------------------------------------------------------------------
*/

$realDataDir = realpath($dataDir);
$realSessionDir = realpath($sessionDir);

if (
    $realDataDir === false ||
    $realSessionDir === false ||
    strpos(
        $realSessionDir,
        $realDataDir . DIRECTORY_SEPARATOR
    ) !== 0
) {
    sendJson([
        'success' => false,
        'error' => 'Nieprawidłowa ścieżka sesji.'
    ], 400);
}

/*
|--------------------------------------------------------------------------
| Sprawdzenie uploadu
|--------------------------------------------------------------------------
*/

if (!isset($_FILES['photo'])) {
    sendJson([
        'success' => false,
        'error' => 'Nie przesłano zdjęcia.'
    ], 400);
}

$file = $_FILES['photo'];

/*
|--------------------------------------------------------------------------
| Błędy PHP uploadu
|--------------------------------------------------------------------------
*/

if ($file['error'] !== UPLOAD_ERR_OK) {

    $errors = [
        UPLOAD_ERR_INI_SIZE   => 'Plik przekracza limit serwera.',
        UPLOAD_ERR_FORM_SIZE  => 'Plik przekracza dozwolony rozmiar.',
        UPLOAD_ERR_PARTIAL    => 'Plik został przesłany tylko częściowo.',
        UPLOAD_ERR_NO_FILE    => 'Nie przesłano pliku.',
        UPLOAD_ERR_NO_TMP_DIR => 'Brak katalogu tymczasowego.',
        UPLOAD_ERR_CANT_WRITE => 'Nie można zapisać pliku.',
        UPLOAD_ERR_EXTENSION  => 'Upload został zatrzymany przez rozszerzenie PHP.'
    ];

    sendJson([
        'success' => false,
        'error' => $errors[$file['error']] ?? 'Nieznany błąd uploadu.'
    ], 400);
}

/*
|--------------------------------------------------------------------------
| Maksymalny rozmiar
|--------------------------------------------------------------------------
*/

$maxFileSize = 20 * 1024 * 1024;

if ($file['size'] > $maxFileSize) {
    sendJson([
        'success' => false,
        'error' => 'Plik jest za duży. Maksymalny rozmiar to 20 MB.'
    ], 413);
}

/*
|--------------------------------------------------------------------------
| Czy to rzeczywiście upload HTTP
|--------------------------------------------------------------------------
*/

if (!is_uploaded_file($file['tmp_name'])) {
    sendJson([
        'success' => false,
        'error' => 'Nieprawidłowy upload pliku.'
    ], 400);
}

/*
|--------------------------------------------------------------------------
| Sprawdzenie obrazu
|--------------------------------------------------------------------------
*/

$imageInfo = @getimagesize($file['tmp_name']);

if ($imageInfo === false) {
    sendJson([
        'success' => false,
        'error' => 'Przesłany plik nie jest prawidłowym obrazem.'
    ], 400);
}

/*
|--------------------------------------------------------------------------
| Dozwolone formaty
|--------------------------------------------------------------------------
*/

$allowedMimeTypes = [
    'image/jpeg' => 'jpg',
    'image/png'  => 'png',
    'image/webp' => 'webp'
];

$mimeType = $imageInfo['mime'] ?? '';

if (!isset($allowedMimeTypes[$mimeType])) {
    sendJson([
        'success' => false,
        'error' => 'Dozwolone są tylko pliki JPG, PNG i WEBP.'
    ], 400);
}

$extension = $allowedMimeTypes[$mimeType];

$photoPath = $sessionDir . '/photo.' . $extension;

/*
|--------------------------------------------------------------------------
| Nie pozwalaj na ponowny upload do tej samej sesji
|--------------------------------------------------------------------------
*/

foreach (['jpg', 'png', 'webp'] as $existingExtension) {

    $existingFile =
        $sessionDir . '/photo.' . $existingExtension;

    if (file_exists($existingFile)) {
        sendJson([
            'success' => false,
            'error' => 'Zdjęcie zostało już przesłane dla tej sesji.'
        ], 409);
    }
}

/*
|--------------------------------------------------------------------------
| Przeniesienie pliku
|--------------------------------------------------------------------------
*/

if (!move_uploaded_file(
    $file['tmp_name'],
    $photoPath
)) {
    sendJson([
        'success' => false,
        'error' => 'Nie udało się zapisać zdjęcia.'
    ], 500);
}

/*
|--------------------------------------------------------------------------
| Aktualizacja state.json
|--------------------------------------------------------------------------
*/

$stateFile = $sessionDir . '/state.json';

$state = [
    'createdOn' => (int) round(microtime(true) * 1000),
    'status' => 'uploading',
    'progress' => 0
];

if (file_exists($stateFile)) {

    $stateJson = file_get_contents($stateFile);

    if ($stateJson !== false) {

        $existingState = json_decode(
            $stateJson,
            true
        );

        if (is_array($existingState)) {
            $state = array_merge(
                $state,
                $existingState
            );
        }
    }
}

$state['status'] = 'uploaded';
$state['progress'] = 0;

/*
 * Zapis atomowy:
 * najpierw plik tymczasowy, potem rename().
 */
$tempStateFile = $stateFile . '.tmp';

$written = file_put_contents(
    $tempStateFile,
    json_encode(
        $state,
        JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE
    ),
    LOCK_EX
);

if ($written === false || !rename($tempStateFile, $stateFile)) {

    @unlink($tempStateFile);

    sendJson([
        'success' => false,
        'error' => 'Nie udało się zapisać stanu sesji.'
    ], 500);
}

/*
|--------------------------------------------------------------------------
| Sukces
|--------------------------------------------------------------------------
*/

sendJson([
    'success' => true,
    'sessionId' => $sessionId,
    'file' => basename($photoPath),
    'status' => 'uploading'
]);