<?php

function enforceSessionRateLimit(
    string $dataDir,
    int $maxSessionsPerMinute,
    array $text,
    string $language
): void {
    $clientIp = $_SERVER['REMOTE_ADDR'] ?? 'unknown';
    $rateLimitFile = $dataDir . '/.rate_limit.json';
    $now = time();
    $rateLimitData = [];

    if (file_exists($rateLimitFile)) {
        $json = file_get_contents($rateLimitFile);

        if ($json !== false) {
            $decoded = json_decode($json, true);

            if (is_array($decoded)) {
                $rateLimitData = $decoded;
            }
        }
    }

    if (!isset($rateLimitData[$clientIp]) || !is_array($rateLimitData[$clientIp])) {
        $rateLimitData[$clientIp] = [];
    }

    $rateLimitData[$clientIp] = array_values(
        array_filter(
            $rateLimitData[$clientIp],
            static function ($timestamp) use ($now) {
                return is_numeric($timestamp)
                    && ((int) $timestamp > $now - 60);
            }
        )
    );

    if (count($rateLimitData[$clientIp]) >= $maxSessionsPerMinute) {
        $oldest = min($rateLimitData[$clientIp]);
        $retryAfter = max(1, 60 - ($now - $oldest));

        http_response_code(429);
        header('Content-Type: text/html; charset=utf-8');

        echo '<!DOCTYPE html>
<html lang="' . htmlspecialchars($language, ENT_QUOTES, 'UTF-8') . '">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>' . htmlspecialchars($text['rate_title'], ENT_QUOTES, 'UTF-8') . '</title>
</head>
<body>
    <main>
        <h1>' . htmlspecialchars($text['rate_title'], ENT_QUOTES, 'UTF-8') . '</h1>
        <p>' . htmlspecialchars($text['rate_limit_prefix'], ENT_QUOTES, 'UTF-8') . ' <strong>'
            . $maxSessionsPerMinute . '</strong> '
            . htmlspecialchars($text['rate_limit_suffix'], ENT_QUOTES, 'UTF-8') . '</p>
        <p>' . htmlspecialchars($text['retry_prefix'], ENT_QUOTES, 'UTF-8') . ' <strong>'
            . $retryAfter . ' ' . htmlspecialchars($text['retry_suffix'], ENT_QUOTES, 'UTF-8') . '</strong></p>
    </main>
</body>
</html>';

        exit;
    }

    $rateLimitData[$clientIp][] = $now;

    file_put_contents(
        $rateLimitFile,
        json_encode(
            $rateLimitData,
            JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE
        ),
        LOCK_EX
    );
}
