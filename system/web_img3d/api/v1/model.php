<?php
declare(strict_types=1);
require __DIR__ . '/_common.php';
requireMethod('GET');
$id = $_GET['systemSessionId'] ?? '';
$version = $_GET['version'] ?? '';
if (!is_string($id) || !validId($id, SYSTEM_SESSION_ID_PATTERN)) {
    apiFail('Nieprawidłowy systemSessionId.', 400);
}
if (!is_string($version) || !preg_match('/^[1-9][0-9]{0,8}$/', $version)) {
    apiFail('Wymagana jest dodatnia wersja GLB.', 400);
}
[$directory] = checkedSystemSession($id);
$pointer = readJsonFile($directory . DIRECTORY_SEPARATOR . 'current-version.json');
if ($pointer === null || !isset($pointer['currentVersion'])
    || !is_int($pointer['currentVersion']) || $pointer['currentVersion'] < (int) $version) {
    apiFail('Wersja GLB nie została opublikowana.', 404);
}
$file = $directory . DIRECTORY_SEPARATOR . 'model.v' . $version . '.glb';
$realFile = realpath($file);
$realDirectory = realpath($directory);
if ($realFile === false || $realDirectory === false
    || strpos($realFile, $realDirectory . DIRECTORY_SEPARATOR) !== 0 || !is_file($realFile)) {
    apiFail('Wersja GLB nie istnieje.', 404);
}
$handle = fopen($realFile, 'rb');
$magic = $handle === false ? false : fread($handle, 4);
if (is_resource($handle)) {
    fclose($handle);
}
if ($magic !== 'glTF') {
    apiFail('Wersja GLB jest nieprawidłowa.', 500);
}
header('Content-Type: model/gltf-binary');
header('Content-Length: ' . filesize($realFile));
header('Cache-Control: public, max-age=31536000, immutable');
header('Content-Disposition: attachment; filename="model.v' . $version . '.glb"');
readfile($realFile);
