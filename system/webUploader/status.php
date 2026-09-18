<?php

// ============================================================
// status.php
//
// GET:
// status.php?sessionId=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
//
// Zwraca zawartość:
// data/{sessionId}/state.json
// ============================================================


// ============================================================
// Tylko GET
// ============================================================

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {

    sendJson(
        405,
        [
            'error' => 'Dozwolona jest tylko metoda GET.'
        ]
    );

}


// ============================================================
// Konfiguracja
// ============================================================

$dataDir = __DIR__ . '/data';


// ============================================================
// Pobranie sessionId
// ============================================================

$sessionId = $_GET['sessionId'] ?? '';


// sessionId generowane przez index.php:
// bin2hex(random_bytes(16))
// = dokładnie 32 znaki [a-f0-9]

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

$sessionDir =
    $dataDir .
    DIRECTORY_SEPARATOR .
    $sessionId;


$stateFile =
    $sessionDir .
    DIRECTORY_SEPARATOR .
    'state.json';


// ============================================================
// Sprawdzenie sesji
// ============================================================

if (!is_dir($sessionDir)) {

    sendJson(
        404,
        [
            'error' => 'Sesja nie istnieje.'
        ]
    );

}


// ============================================================
// Sprawdzenie state.json
// ============================================================

if (!is_file($stateFile)) {

    sendJson(
        404,
        [
            'error' => 'Nie znaleziono pliku state.json.'
        ]
    );

}


// ============================================================
// Odczyt state.json
// ============================================================

$content =
    file_get_contents($stateFile);


if ($content === false) {

    sendJson(
        500,
        [
            'error' =>
                'Nie udało się odczytać stanu sesji.'
        ]
    );

}


// ============================================================
// Parsowanie JSON
// ============================================================

$state =
    json_decode(
        $content,
        true
    );


if (!is_array($state)) {

    sendJson(
        500,
        [
            'error' =>
                'Plik state.json zawiera nieprawidłowy JSON.'
        ]
    );

}


// ============================================================
// Walidacja podstawowych pól
// ============================================================

if (!isset($state['createdOn'])) {
    $state['createdOn'] = null;
}

if (!isset($state['status'])) {
    $state['status'] = 'unknown';
}

if (!isset($state['progress'])) {
    $state['progress'] = 0;
}


// ============================================================
// Jeżeli status = ready
// ============================================================
//
// Możemy automatycznie zwrócić ścieżkę do GLB.
//
// W state.json proces generujący GLB może opcjonalnie
// zapisać:
//
// "glb": "model.glb"
//
// Jeżeli tego pola nie ma, domyślnie używamy model.glb.
// ============================================================

if ($state['status'] === 'ready') {

    $glbFile =
        $state['glb']
        ?? 'model.glb';


    // Nie pozwalamy, aby state.json zwrócił
    // ścieżkę wychodzącą poza katalog sesji.
    //
    // Dopuszczamy tylko zwykłą nazwę pliku.
    if (
        !is_string($glbFile) ||
        !preg_match(
            '/^[a-zA-Z0-9._-]+\.glb$/i',
            $glbFile
        )
    ) {

        sendJson(
            500,
            [
                'error' =>
                    'Nieprawidłowa nazwa pliku GLB.'
            ]
        );

    }


    $glbPath =
        $sessionDir .
        DIRECTORY_SEPARATOR .
        $glbFile;


    // Jeżeli proces ustawił ready, ale GLB jeszcze
    // fizycznie nie istnieje, nie udajemy, że jest gotowy.
    if (!is_file($glbPath)) {

        sendJson(
            500,
            [
                'error' =>
                    'Sesja ma status ready, ale plik GLB nie istnieje.'
            ]
        );

    }


    // Ścieżka względna względem strony.
    $state['glb'] =
        'data/' .
        $sessionId .
        '/' .
        $glbFile;

}


// ============================================================
// Odpowiedź
// ============================================================

sendJson(
    200,
    $state
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

    // Zapobiega cache'owaniu statusu przez przeglądarkę.
    header(
        'Cache-Control: no-store, no-cache, must-revalidate, max-age=0'
    );

    header(
        'Pragma: no-cache'
    );

    echo json_encode(
        $data,
        JSON_UNESCAPED_UNICODE |
        JSON_UNESCAPED_SLASHES
    );

    exit;
}