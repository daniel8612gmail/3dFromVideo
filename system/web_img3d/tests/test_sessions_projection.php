<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}

function checkProjection(bool $condition, string $message): void
{
    if (!$condition) {
        fwrite(STDERR, "FAIL: $message\n");
        exit(1);
    }
}

$root = dirname(__DIR__) . DIRECTORY_SEPARATOR . 'data'
    . DIRECTORY_SEPARATOR . 'system-sessions';
$sessionId = bin2hex(random_bytes(16));
$sessionDir = $root . DIRECTORY_SEPARATOR . $sessionId;
$framesDir = $sessionDir . DIRECTORY_SEPARATOR . 'frames';
mkdir($framesDir . DIRECTORY_SEPARATOR . 'frame_0001', 0750, true);
mkdir($framesDir . DIRECTORY_SEPARATOR . 'frame_0002', 0750, true);
mkdir($framesDir . DIRECTORY_SEPARATOR . 'frame_0003', 0750, true);
mkdir($framesDir . DIRECTORY_SEPARATOR . 'frame_0004', 0750, true);

file_put_contents($sessionDir . DIRECTORY_SEPARATOR . 'session.json', json_encode([
    'systemSessionId' => $sessionId,
    'status' => 'processing',
    'deviceId' => 'must-not-be-returned',
]));
file_put_contents($sessionDir . DIRECTORY_SEPARATOR . 'status.json', json_encode([
    'status' => 'processing',
    'progress' => 25,
]));
file_put_contents($framesDir . DIRECTORY_SEPARATOR . 'frame_0001' . DIRECTORY_SEPARATOR . 'frame.json', json_encode([
    'frameId' => 'frame_0001',
    'sequence' => 1,
    'status' => 'processing',
    'progress' => 25,
    'stage' => 'moge3',
    'message' => 'Przetwarzanie obrazu',
]));
file_put_contents($framesDir . DIRECTORY_SEPARATOR . 'frame_0002' . DIRECTORY_SEPARATOR . 'frame.json', json_encode([
    'frameId' => 'frame_0002',
    'sequence' => 2,
    'stage' => 'C:\\private\\workspace\\image',
    'message' => 'RuntimeException: C:\\private\\workspace\\image; token=abc123',
]));
file_put_contents($framesDir . DIRECTORY_SEPARATOR . 'frame_0003' . DIRECTORY_SEPARATOR . 'frame.json', json_encode([
    'frameId' => 'frame_0003',
    'sequence' => 3,
]));
file_put_contents($framesDir . DIRECTORY_SEPARATOR . 'frame_0004' . DIRECTORY_SEPARATOR . 'frame.json', json_encode([
    'frameId' => 'frame_0004',
    'sequence' => 4,
    'message' => "status\x00\x01binary",
]));

$script = '$_SERVER["REQUEST_METHOD"]="GET"; $_GET["systemSessionId"]=$argv[1]; require $argv[2];';
$command = [PHP_BINARY, '-n', '-r', $script, $sessionId, dirname(__DIR__) . DIRECTORY_SEPARATOR . 'api'
    . DIRECTORY_SEPARATOR . 'v1' . DIRECTORY_SEPARATOR . 'sessions.php'];
$process = proc_open($command, [
    0 => ['pipe', 'r'],
    1 => ['pipe', 'w'],
    2 => ['pipe', 'w'],
], $pipes);

try {
    checkProjection(is_resource($process), 'starts the sessions endpoint subprocess');
    fclose($pipes[0]);
    $output = stream_get_contents($pipes[1]);
    $errors = stream_get_contents($pipes[2]);
    fclose($pipes[1]);
    fclose($pipes[2]);
    $exitCode = proc_close($process);
    checkProjection($exitCode === 0, 'sessions endpoint exits successfully: ' . $errors);
    $payload = json_decode($output, true);
    checkProjection(is_array($payload) && ($payload['success'] ?? false) === true, 'returns a successful session projection');
    $frames = $payload['frames'] ?? [];
    checkProjection(count($frames) === 4, 'returns all fixture frames');
    checkProjection($frames[0]['stage'] === 'moge3', 'projects an allowed processing stage');
    checkProjection($frames[0]['message'] === 'Przetwarzanie obrazu', 'projects a safe display message');
    checkProjection($frames[1]['stage'] === null && $frames[1]['message'] === null, 'omits path, exception and secret-shaped values');
    checkProjection($frames[2]['stage'] === null && $frames[2]['message'] === null, 'uses nullable fallbacks for missing fields');
    checkProjection($frames[3]['message'] === null, 'omits binary/control-character message data');
    checkProjection(strpos($output, 'private') === false && strpos($output, 'token=') === false, 'does not serialize rejected sensitive text');
} finally {
    if (is_resource($process)) {
        proc_terminate($process);
        proc_close($process);
    }
    $removeTree = static function (string $path) use (&$removeTree): void {
        if (is_dir($path) && !is_link($path)) {
            foreach (scandir($path) ?: [] as $entry) {
                if ($entry !== '.' && $entry !== '..') {
                    $removeTree($path . DIRECTORY_SEPARATOR . $entry);
                }
            }
            rmdir($path);
        } elseif (file_exists($path) || is_link($path)) {
            unlink($path);
        }
    };
    $removeTree($sessionDir);
}

echo "PHP sessions projection tests passed.\n";
