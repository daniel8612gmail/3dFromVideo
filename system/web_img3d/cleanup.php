<?php

// ============================================================
// cleanup.php
//
// Usuwa stare katalogi sesji.
//
// Plik systemStatus.json przechowuje datę ostatniego cleanup.
//
// Przykład:
//
// {
//     "lastCleanup": "2026-09-18"
// }
//
// Cleanup wykonywany jest tylko wtedy, gdy ostatni cleanup
// nie był wykonany dzisiaj.
// ============================================================


// ============================================================
// Konfiguracja
// ============================================================

$dataDir = __DIR__ . '/data';

// Jak długo przechowujemy sesje?
// 24 godziny = 86400 sekund.
$sessionLifetime = 24 * 60 * 60;

$systemStatusFile =
    $dataDir . '/systemStatus.json';


// ============================================================
// Przygotowanie katalogu data
// ============================================================

if (!is_dir($dataDir)) {

    mkdir(
        $dataDir,
        0755,
        true
    );

}


// ============================================================
// Aktualna data
// ============================================================

$today =
    date('Y-m-d');


// ============================================================
// Odczyt systemStatus.json
// ============================================================

$lastCleanup = null;

if (is_file($systemStatusFile)) {

    $content =
        file_get_contents(
            $systemStatusFile
        );

    if ($content !== false) {

        $status =
            json_decode(
                $content,
                true
            );

        if (is_array($status)) {

            $lastCleanup =
                $status['lastCleanup']
                ?? null;

        }

    }

}


// ============================================================
// Jeżeli cleanup był już dzisiaj,
// nic więcej nie robimy.
// ============================================================

if ($lastCleanup === $today) {

    return;

}


// ============================================================
// Cleanup
// ============================================================

$now =
    time();

$deletedSessions = 0;


// Pobieramy zawartość data/
$entries =
    scandir($dataDir);


if ($entries !== false) {

    foreach ($entries as $entry) {

        // Pomijamy . i ..
        if (
            $entry === '.' ||
            $entry === '..'
        ) {
            continue;
        }


        // systemStatus.json nie jest sesją
        if ($entry === 'systemStatus.json') {
            continue;
        }


        // Nie ruszamy .htaccess
        if ($entry === '.htaccess') {
            continue;
        }


        // Sesje mają 32 znaki hex.
        //
        // To dodatkowa ochrona przed przypadkowym
        // usunięciem innego pliku/katalogu.
        if (
            !preg_match(
                '/^[a-f0-9]{32}$/',
                $entry
            )
        ) {
            continue;
        }


        $sessionDir =
            $dataDir .
            DIRECTORY_SEPARATOR .
            $entry;


        if (!is_dir($sessionDir)) {
            continue;
        }


        // ====================================================
        // Sprawdzenie wieku katalogu
        // ====================================================

        $modified =
            filemtime($sessionDir);


        if ($modified === false) {
            continue;
        }


        $age =
            $now - $modified;


        if ($age < $sessionLifetime) {
            continue;
        }


        // ====================================================
        // Usunięcie sesji
        // ====================================================

        if (deleteDirectory($sessionDir)) {

            $deletedSessions++;

        }

    }

}


// ============================================================
// Zapis informacji o cleanup
// ============================================================

$systemStatus = [
    'lastCleanup' => $today
];


file_put_contents(
    $systemStatusFile,
    json_encode(
        $systemStatus,
        JSON_PRETTY_PRINT |
        JSON_UNESCAPED_UNICODE
    ),
    LOCK_EX
);


// ============================================================
// Funkcja rekurencyjnego usuwania katalogu
// ============================================================

function deleteDirectory(
    string $directory
): bool {

    if (!is_dir($directory)) {
        return false;
    }


    $entries =
        scandir($directory);


    if ($entries === false) {
        return false;
    }


    foreach ($entries as $entry) {

        if (
            $entry === '.' ||
            $entry === '..'
        ) {
            continue;
        }


        $path =
            $directory .
            DIRECTORY_SEPARATOR .
            $entry;


        if (is_dir($path)) {

            if (!deleteDirectory($path)) {
                return false;
            }

        } else {

            if (!unlink($path)) {
                return false;
            }

        }

    }


    return rmdir($directory);
}