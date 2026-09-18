<?php

// ============================================================
// upload.php
//
// Oczekuje:
// POST upload.php?sessionId=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
//
// Pole multipart/form-data:
// photo
//
// Zapisuje:
// data/{sessionId}/photo.{ext}
//
// Aktualizuje:
// data/{sessionId}/state.json
// ============================================================


// ============================================================
// Konfiguracja
// ============================================================

$dataDir = __DIR__ . '/data';

// Maksymalny rozmiar zdjęcia: 20 MB
$maxFileSize = 20 * 1024 * 1024;


// ============================================================
// Tylko POST
// ============================================================

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {

    sendJson(
        405,
        [
            'error' => 'Dozwolona jest tylko metoda POST.'
        ]
    );

}


// ============================================================
// Pobranie sessionId
// ============================================================

$sessionId = $_GET['sessionId'] ?? '';


// sessionId generowane przez index.php ma dokładnie
// 32 znaki hex, ponieważ używamy bin2hex(random_bytes(16)).
if (!preg_match('/^[a-f0-9]{32}$/', $sessionId)) {

    sendJson(
        400,
        [
            'error' => 'Nieprawidłowy identyfikator sesji.'
        ]
    );

}


// ============================================================
// Katalog sesji
// ============================================================

$sessionDir = $dataDir . '/' . $sessionId;

$realDataDir = realpath($dataDir);
$realSessionDir = realpath($sessionDir);


// Sesja musi istnieć.
if (
    $realDataDir === false ||
    $realSessionDir === false ||
    !is_dir($realSessionDir)
) {

    sendJson(
        404,
        [
            'error' => 'Sesja nie istnieje.'
        ]
    );

}


// Dodatkowe zabezpieczenie przed wyjściem poza /data.
if (
    strpos(
        $realSessionDir,
        $realDataDir . DIRECTORY_SEPARATOR
    ) !== 0
) {

    sendJson(
        400,
        [
            'error' => 'Nieprawidłowy katalog sesji.'
        ]
    );

}


// ============================================================
// Sprawdzenie uploadu
// ============================================================

if (!isset($_FILES['photo'])) {

    sendJson(
        400,
        [
            'error' => 'Nie przesłano zdjęcia.'
        ]
    );

}


$file = $_FILES['photo'];


// ============================================================
// Błąd PHP podczas uploadu
// ============================================================

if ($file['error'] !== UPLOAD_ERR_OK) {

    $errors = [
        UPLOAD_ERR_INI_SIZE =>
            'Plik przekracza limit ustawiony przez serwer.',

        UPLOAD_ERR_FORM_SIZE =>
            'Plik przekracza dozwolony rozmiar.',

        UPLOAD_ERR_PARTIAL =>
            'Plik został przesłany tylko częściowo.',

        UPLOAD_ERR_NO_FILE =>
            'Nie przesłano pliku.',

        UPLOAD_ERR_NO_TMP_DIR =>
            'Brak katalogu tymczasowego.',

        UPLOAD_ERR_CANT_WRITE =>
            'Nie udało się zapisać pliku na serwerze.',

        UPLOAD_ERR_EXTENSION =>
            'Upload został zatrzymany przez rozszerzenie PHP.'
    ];

    sendJson(
        400,
        [
            'error' =>
                $errors[$file['error']]
                ?? 'Nieznany błąd uploadu.'
        ]
    );

}


// ============================================================
// Rozmiar
// ============================================================

if ($file['size'] <= 0) {

    sendJson(
        400,
        [
            'error' => 'Przesłany plik jest pusty.'
        ]
    );

}


if ($file['size'] > $maxFileSize) {

    sendJson(
        413,
        [
            'error' =>
                'Zdjęcie jest zbyt duże. Maksymalny rozmiar to 20 MB.'
        ]
    );

}


// ============================================================
// Sprawdzenie czy to rzeczywiście obraz
// ============================================================

$tmpFile = $file['tmp_name'];


// is_uploaded_file zabezpiecza przed wskazaniem
// dowolnego pliku znajdującego się na serwerze.
if (!is_uploaded_file($tmpFile)) {

    sendJson(
        400,
        [
            'error' => 'Nieprawidłowy upload pliku.'
        ]
    );

}


// getimagesize analizuje zawartość pliku,
// a nie tylko jego rozszerzenie.
$imageInfo = @getimagesize($tmpFile);

if ($imageInfo === false) {

    sendJson(
        400,
        [
            'error' => 'Przesłany plik nie jest prawidłowym obrazem.'
        ]
    );

}


// ============================================================
// Dozwolone formaty
// ============================================================

$allowedMimeTypes = [
    'image/jpeg' => 'jpg',
    'image/png'  => 'png',
    'image/webp' => 'webp'
];

$mimeType = $imageInfo['mime'] ?? '';

if (!isset($allowedMimeTypes[$mimeType])) {

    sendJson(
        415,
        [
            'error' =>
                'Niedozwolony format zdjęcia. Dozwolone: JPG, PNG, WEBP.'
        ]
    );

}

$extension = $allowedMimeTypes[$mimeType];


// ============================================================
// Nazwa pliku
// ============================================================
//
// Nie używamy nazwy przesłanej przez użytkownika.
// Dzięki temu np.:
//
// ../../plik.php
//
// nie może wpłynąć na lokalizację zapisu.
//
// Nazwa jest zawsze:
//
// photo.jpg
// photo.png
// photo.webp
// ============================================================

$photoPath =
    $realSessionDir .
    DIRECTORY_SEPARATOR .
    'photo.' .
    $extension;


// ============================================================
// Nie pozwalamy nadpisać istniejącego zdjęcia
// ============================================================

if (file_exists($photoPath)) {

    sendJson(
        409,
        [
            'error' =>
                'Do tej sesji zostało już przesłane zdjęcie.'
        ]
    );

}


// ============================================================
// Zapis pliku
// ============================================================

if (!move_uploaded_file($tmpFile, $photoPath)) {

    sendJson(
        500,
        [
            'error' =>
                'Nie udało się zapisać zdjęcia na serwerze.'
        ]
    );

}


// ============================================================
// State
// ============================================================

$stateFile =
    $realSessionDir .
    DIRECTORY_SEPARATOR .
    'state.json';


$state = [
    'createdOn' => null,
    'status' => 'uploading',
    'progress' => 0
];


// Odczytujemy istniejący state.json.
if (file_exists($stateFile)) {

    $stateContent =
        file_get_contents($stateFile);

    if ($stateContent !== false) {

        $existingState =
            json_decode(
                $stateContent,
                true
            );

        if (is_array($existingState)) {

            $state =
                array_merge(
                    $state,
                    $existingState
                );

        }

    }

}


// Ustawiamy nowy status.
$state['status'] = 'uploading';
$state['progress'] = 0;


// Zapis atomowy:
// najpierw zapisujemy plik tymczasowy,
// potem podmieniamy state.json.
//
// Dzięki temu status.php nie powinien zobaczyć
// częściowo zapisanego JSON-a.

$tempStateFile =
    $stateFile .
    '.tmp';


$stateJson =
    json_encode(
        $state,
        JSON_PRETTY_PRINT |
        JSON_UNESCAPED_UNICODE |
        JSON_UNESCAPED_SLASHES
    );


if (
    $stateJson === false ||
    file_put_contents(
        $tempStateFile,
        $stateJson,
        LOCK_EX
    ) === false
) {

    // Zdjęcie zostało już zapisane, więc informujemy
    // o błędzie aktualizacji statusu.
    sendJson(
        500,
        [
            'error' =>
                'Zdjęcie zapisano, ale nie udało się zaktualizować statusu.'
        ]
    );

}


if (!rename($tempStateFile, $stateFile)) {

    @unlink($tempStateFile);

    sendJson(
        500,
        [
            'error' =>
                'Zdjęcie zapisano, ale nie udało się zaktualizować statusu.'
        ]
    );

}


// ============================================================
// Odpowiedź
// ============================================================

sendJson(
    200,
    [
        'success' => true,
        'sessionId' => $sessionId,
        'file' => 'photo.' . $extension,
        'status' => 'uploading'
    ]
);


// ============================================================
// Funkcja JSON response
// ============================================================

function sendJson(
    int $httpStatus,
    array $data
): never {

    http_response_code($httpStatus);

    header(
        'Content-Type: application/json; charset=utf-8'
    );

    echo json_encode(
        $data,
        JSON_UNESCAPED_UNICODE |
        JSON_UNESCAPED_SLASHES
    );

    exit;
}