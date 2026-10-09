<?php

$sessionId = $_GET['sessionId'] ?? '';

if (!is_string($sessionId) || !preg_match('/^[a-f0-9]{32}$/', $sessionId)) {
    http_response_code(400);
    exit('Nieprawidłowy session ID');
}

$dataDir = __DIR__ . '/data';
$sessionDir = $dataDir . DIRECTORY_SEPARATOR . $sessionId;
$file = $sessionDir . DIRECTORY_SEPARATOR . 'model.glb';
$realDataDir = realpath($dataDir);
$realSessionDir = realpath($sessionDir);
$realFile = realpath($file);

if (
    $realDataDir === false
    || $realSessionDir === false
    || $realFile === false
    || strpos($realSessionDir, $realDataDir . DIRECTORY_SEPARATOR) !== 0
    || strpos($realFile, $realSessionDir . DIRECTORY_SEPARATOR) !== 0
) {
    http_response_code(404);
    exit('Plik GLB nie istnieje');
}

header('Content-Type: model/gltf-binary');
header('Content-Length: ' . filesize($realFile));
header('Cache-Control: no-store');
header('Content-Disposition: attachment; filename="model.glb"; filename*=UTF-8\'\'model.glb');

readfile($realFile);