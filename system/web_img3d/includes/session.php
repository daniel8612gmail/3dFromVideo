<?php

function loadExistingSession(string $dataDir, $requestedSessionId): ?array
{
    if (
        !is_string($requestedSessionId)
        || !preg_match('/^[a-f0-9]{32}$/', $requestedSessionId)
    ) {
        return null;
    }

    $sessionDir = $dataDir . DIRECTORY_SEPARATOR . $requestedSessionId;
    $stateFile = $sessionDir . DIRECTORY_SEPARATOR . 'state.json';

    if (!is_dir($sessionDir) || !is_file($stateFile)) {
        return null;
    }

    $stateJson = file_get_contents($stateFile);
    $state = $stateJson === false ? null : json_decode($stateJson, true);

    if (
        !is_array($state)
        || !isset($state['createdOn'])
        || !is_numeric($state['createdOn'])
    ) {
        return null;
    }

    return [
        'sessionId' => $requestedSessionId,
        'createdOn' => (int) $state['createdOn']
    ];
}

function createSession(string $dataDir, string $sessionCreateError): array
{
    $sessionId = bin2hex(random_bytes(16));
    $createdOn = (int) round(microtime(true) * 1000);
    $sessionDir = $dataDir . DIRECTORY_SEPARATOR . $sessionId;

    if (!mkdir($sessionDir, 0755, true)) {
        http_response_code(500);
        exit($sessionCreateError);
    }

    $state = [
        'createdOn' => $createdOn,
        'status' => 'oczekiwanie',
        'progress' => 0
    ];

    file_put_contents(
        $sessionDir . DIRECTORY_SEPARATOR . 'state.json',
        json_encode(
            $state,
            JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE
        ),
        LOCK_EX
    );

    return [
        'sessionId' => $sessionId,
        'createdOn' => $createdOn
    ];
}
