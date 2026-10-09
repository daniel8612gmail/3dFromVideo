<?php

require_once __DIR__ . '/cleanup.php';
require_once __DIR__ . '/includes/language.php';
require_once __DIR__ . '/includes/rate-limit.php';
require_once __DIR__ . '/includes/session.php';

define('IMG3D_FRONT_CONTROLLER', true);

$dataDir = __DIR__ . '/data';
$maxSessionsPerMinute = 30;
$language = resolveLanguage();
$text = getTranslations($language);

$session = loadExistingSession(
    $dataDir,
    $_GET['sessionId'] ?? null
);

if ($session === null) {
    enforceSessionRateLimit(
        $dataDir,
        $maxSessionsPerMinute,
        $text,
        $language
    );

    $session = createSession(
        $dataDir,
        $text['session_create_error']
    );
}

$sessionId = $session['sessionId'];
$createdOn = $session['createdOn'];

require __DIR__ . '/templates/index.php';
