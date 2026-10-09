<?php

$sessionId = $_GET['sessionId'] ?? '';

if (!is_string($sessionId) || !preg_match('/^[a-f0-9]{32}$/', $sessionId)) {
    http_response_code(400);
    exit('Invalid session ID.');
}

$dataDir = __DIR__ . '/data';
$sessionDir = $dataDir . DIRECTORY_SEPARATOR . $sessionId;
$realDataDir = realpath($dataDir);
$realSessionDir = realpath($sessionDir);

if (
    $realDataDir === false
    || $realSessionDir === false
    || strpos($realSessionDir, $realDataDir . DIRECTORY_SEPARATOR) !== 0
) {
    http_response_code(404);
    exit('Photo not found.');
}

$photoTypes = [
    'jpg' => 'image/jpeg',
    'png' => 'image/png',
    'webp' => 'image/webp'
];

foreach ($photoTypes as $extension => $contentType) {
    $photoPath = $realSessionDir . DIRECTORY_SEPARATOR . 'photo.' . $extension;

    if (!is_file($photoPath)) {
        continue;
    }

    header('Content-Type: ' . $contentType);
    header('Content-Length: ' . (string) filesize($photoPath));
    header('Cache-Control: no-store');
    header('X-Content-Type-Options: nosniff');
    readfile($photoPath);
    exit;
}

http_response_code(404);
exit('Photo not found.');
