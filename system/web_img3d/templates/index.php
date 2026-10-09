<?php

if (!defined('IMG3D_FRONT_CONTROLLER')) {
    http_response_code(404);
    exit;
}

$clientConfig = [
    'sessionId' => $sessionId,
    'createdOn' => $createdOn,
    'language' => $language,
    'text' => $text,
    'photoUrl' => 'get-photo.php?sessionId=' . rawurlencode($sessionId)
];

?>
<!DOCTYPE html>
<html lang="<?= htmlspecialchars($language, ENT_QUOTES, 'UTF-8') ?>">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Image → 3D</title>
    <script type="importmap">
    {
        "imports": {
            "three": "https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js",
            "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.180.0/examples/jsm/"
        }
    }
    </script>
    <link rel="stylesheet" href="assets/css/index.css">
</head>
<body>
    <main class="container">
        <nav class="language-switcher" aria-label="Language / Język">
            <a href="?lang=pl&amp;sessionId=<?= rawurlencode($sessionId) ?>"
               lang="pl"
               hreflang="pl"
               <?= $language === 'pl' ? 'aria-current="page"' : '' ?>>Polski</a>
            <a href="?lang=en&amp;sessionId=<?= rawurlencode($sessionId) ?>"
               lang="en"
               hreflang="en"
               <?= $language === 'en' ? 'aria-current="page"' : '' ?>>English</a>
        </nav>

        <h1>Image → 3D</h1>
        <p><?= htmlspecialchars($text['description'], ENT_QUOTES, 'UTF-8') ?></p>
        <p><?= htmlspecialchars($text['description_details'], ENT_QUOTES, 'UTF-8') ?></p>

        <section class="session-info" aria-label="<?= htmlspecialchars($text['session_id'], ENT_QUOTES, 'UTF-8') ?>">
            <div>
                <span class="label"><?= htmlspecialchars($text['session_id'], ENT_QUOTES, 'UTF-8') ?></span>
                <span id="sessionId"></span>
            </div>
            <div>
                <span class="label"><?= htmlspecialchars($text['created'], ENT_QUOTES, 'UTF-8') ?></span>
                <span id="createdOn"></span>
            </div>
        </section>

        <section class="upload-section">
            <label for="photoInput" class="button" id="uploadButton" hidden>
                <?= htmlspecialchars($text['upload_photo'], ENT_QUOTES, 'UTF-8') ?>
            </label>
            <input type="file" id="photoInput" accept="image/jpeg,image/png,image/webp">
            <button type="button" class="button new-session" id="newSessionButton">
                <?= htmlspecialchars($text['new_session'], ENT_QUOTES, 'UTF-8') ?>
            </button>
            <div class="filename" id="filename"></div>
            <div class="image-preview" id="imagePreviewWrapper">
                <img id="imagePreview" alt="<?= htmlspecialchars($text['image_preview'], ENT_QUOTES, 'UTF-8') ?>">
            </div>
        </section>

        <section class="status" id="status-container" aria-live="polite">
            <div>
                <strong><?= htmlspecialchars($text['status_label'], ENT_QUOTES, 'UTF-8') ?></strong>
                <span id="statusText"><?= htmlspecialchars($text['waiting'], ENT_QUOTES, 'UTF-8') ?></span>
            </div>
            <div class="progress-container">
                <div class="progress-bar" id="progressBar"></div>
            </div>
            <div class="progress-text" id="progressText">0%</div>
        </section>

        <div class="error" id="errorBox" role="alert"></div>
        <div id="viewer">
            <div class="viewer-message">
                <?= htmlspecialchars($text['viewer_placeholder'], ENT_QUOTES, 'UTF-8') ?>
            </div>
        </div>
    </main>

    <script id="img3dConfig" type="application/json"><?= json_encode(
        $clientConfig,
        JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_APOS | JSON_HEX_AMP | JSON_HEX_QUOT
    ) ?></script>
    <script type="module" src="assets/js/app.js"></script>
</body>
</html>
