<?php
declare(strict_types=1);
require __DIR__ . '/_common.php';

$method = $_SERVER['REQUEST_METHOD'] ?? '';
if ($method === 'POST') {
    $request = readJsonRequest();
    $deviceId = $request['deviceId'] ?? null;
    if (!is_string($deviceId) || trim($deviceId) === '' || strlen($deviceId) > 128) {
        apiFail('deviceId jest wymaganym tekstowym identyfikatorem (1–128 znaków).', 400);
    }

    $root = ensureSystemSessionsRoot();
    $leases = $root . DIRECTORY_SEPARATOR . 'leases';
    if (!is_dir($leases) && !mkdir($leases, 0750, true) && !is_dir($leases)) {
        apiFail('Nie można zainicjować blokady urządzenia.', 500);
    }
    $leasePath = $leases . DIRECTORY_SEPARATOR . hash('sha256', $deviceId) . '.json';
    $lock = fopen($leasePath . '.lock', 'c+');
    if ($lock === false || !flock($lock, LOCK_EX)) {
        if (is_resource($lock)) {
            fclose($lock);
        }
        apiFail('Nie można zablokować urządzenia.', 500);
    }
    try {
        $lease = readJsonFile($leasePath);
        if (isset($lease['systemSessionId']) && validId($lease['systemSessionId'], SYSTEM_SESSION_ID_PATTERN)) {
            $existingDir = $root . DIRECTORY_SEPARATOR . $lease['systemSessionId'];
            $existing = readJsonFile($existingDir . DIRECTORY_SEPARATOR . 'session.json');
            if ($existing !== null && ($existing['deviceId'] ?? null) === $deviceId
                && ($existing['acceptingFrames'] ?? false) === true) {
                apiJson(['success' => true, 'systemSessionId' => $lease['systemSessionId'],
                    'status' => $existing['status'], 'reused' => true], 200);
            }
        }

        $id = bin2hex(random_bytes(16));
        $directory = $root . DIRECTORY_SEPARATOR . $id;
        foreach (['frames', 'queue', 'models'] as $name) {
            if (!mkdir($directory . DIRECTORY_SEPARATOR . $name, 0750, true)
                && !is_dir($directory . DIRECTORY_SEPARATOR . $name)) {
                throw new RuntimeException('Nie można utworzyć katalogu sesji.');
            }
        }
        $session = [
            'schemaVersion' => 1,
            'systemSessionId' => $id,
            'deviceId' => $deviceId,
            'createdAt' => (int) floor(microtime(true) * 1000),
            'status' => 'collecting',
            'acceptingFrames' => true,
            'frameCount' => 0,
            'currentVersion' => 0,
            'arSessionEpochs' => [],
            'cameraProfile' => null,
        ];
        atomicJsonWrite($directory . DIRECTORY_SEPARATOR . 'session.json', $session);
        atomicJsonWrite($directory . DIRECTORY_SEPARATOR . 'status.json', [
            'status' => 'collecting', 'progress' => 0, 'completedFrames' => 0, 'totalFrames' => 0,
        ]);
        atomicJsonWrite($leasePath, ['deviceId' => $deviceId, 'systemSessionId' => $id]);
        apiJson(['success' => true, 'systemSessionId' => $id, 'status' => 'collecting', 'reused' => false], 201);
    } catch (Throwable $error) {
        apiFail('Nie udało się utworzyć sesji systemowej.', 500);
    } finally {
        flock($lock, LOCK_UN);
        fclose($lock);
    }
}

if ($method === 'GET') {
    $id = $_GET['systemSessionId'] ?? '';
    [$directory, $session] = checkedSystemSession(is_string($id) ? $id : '');
    $status = readJsonFile($directory . DIRECTORY_SEPARATOR . 'status.json') ?? [];
    $session['status'] = $status['status'] ?? $session['status'] ?? 'unknown';
    $session['currentVersion'] = $status['currentVersion'] ?? 0;
    unset($session['deviceId']);
    $frames = [];
    $frameRoot = $directory . DIRECTORY_SEPARATOR . 'frames';
    foreach (glob($frameRoot . DIRECTORY_SEPARATOR . '*' . DIRECTORY_SEPARATOR . 'frame.json') ?: [] as $framePath) {
        $frame = readJsonFile($framePath);
        if ($frame !== null) {
            $stage = $frame['stage'] ?? null;
            if (!is_string($stage) || !in_array($stage, [
                'starting', 'prepare_image', 'moge3', 'generate3D', 'export_glb',
            ], true)) {
                $stage = null;
            }

            $message = $frame['message'] ?? null;
            if (!is_string($message) || !in_array($message, [
                'Przetwarzanie obrazu', 'Generowanie modelu 3D', 'Eksport modelu 3D',
            ], true)) {
                $message = null;
            }

            $frames[] = [
                'frameId' => $frame['frameId'] ?? null,
                'sequence' => $frame['sequence'] ?? null,
                'status' => $frame['status'] ?? 'unknown',
                'progress' => $frame['progress'] ?? 0,
                'error' => $frame['error'] ?? null,
                'stage' => $stage,
                'message' => $message,
            ];
        }
    }
    usort($frames, static fn(array $a, array $b): int => ($a['sequence'] ?? 0) <=> ($b['sequence'] ?? 0));
    apiJson(['success' => true, 'systemSessionId' => $id, 'session' => $session,
        'progress' => $status, 'frames' => $frames]);
}

header('Allow: GET, POST');
apiFail('Niedozwolona metoda HTTP.', 405);
