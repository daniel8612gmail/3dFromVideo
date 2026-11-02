<?php
declare(strict_types=1);
require __DIR__ . '/_common.php';
requireMethod('POST');
$request = readJsonRequest();
$id = $request['systemSessionId'] ?? null;
[$directory, $session] = checkedSystemSession(is_string($id) ? $id : '');
$lock = fopen($directory . DIRECTORY_SEPARATOR . 'session.lock', 'c+');
if ($lock === false || !flock($lock, LOCK_EX)) {
    if (is_resource($lock)) {
        fclose($lock);
    }
    apiFail('Nie można zablokować sesji.', 500);
}
$wasAlreadyClosed = false;
try {
    $session = readJsonFile($directory . DIRECTORY_SEPARATOR . 'session.json') ?? $session;
    $wasAlreadyClosed = ($session['acceptingFrames'] ?? false) !== true;
    if (!$wasAlreadyClosed) {
        $session['acceptingFrames'] = false;
        $session['status'] = 'closing';
        $session['closedAt'] = (int) floor(microtime(true) * 1000);
        atomicJsonWrite($directory . DIRECTORY_SEPARATOR . 'session.json', $session);
        $status = readJsonFile($directory . DIRECTORY_SEPARATOR . 'status.json') ?? [];
        $total = max((int) ($status['totalFrames'] ?? 0), (int) ($session['frameCount'] ?? 0));
        $completed = (int) ($status['completedFrames'] ?? 0);
        $status['status'] = ($completed >= $total) ? 'complete' : 'closing';
        $status['totalFrames'] = $total;
        atomicJsonWrite($directory . DIRECTORY_SEPARATOR . 'status.json', $status);
    }
} finally {
    flock($lock, LOCK_UN);
    fclose($lock);
}
if (!$wasAlreadyClosed) {
    $deviceId = $session['deviceId'] ?? null;
    if (is_string($deviceId)) {
        updateLease(ensureSystemSessionsRoot(), $deviceId, null, $id);
    }
}
$latestStatus = readJsonFile($directory . DIRECTORY_SEPARATOR . 'status.json') ?? [];
$responseStatus = $latestStatus['status'] ?? $session['status'] ?? 'closing';
apiJson(['success' => true, 'systemSessionId' => $id, 'status' => $responseStatus,
    'acceptingFrames' => false, 'idempotent' => $wasAlreadyClosed]);
