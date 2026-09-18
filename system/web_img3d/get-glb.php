<?php

$sessionId = $_GET['sessionId'] ?? '';

if (!preg_match('/^[a-zA-Z0-9_-]+$/', $sessionId)) {
    http_response_code(400);
    exit('Nieprawidłowy session ID');
}

$file = __DIR__ . "/data/{$sessionId}/model.glb";

if (!is_file($file)) {
    http_response_code(404);
    exit('Plik GLB nie istnieje');
}

header('Content-Type: model/gltf-binary');
header('Content-Length: ' . filesize($file));
header('Cache-Control: no-cache');

readfile($file);