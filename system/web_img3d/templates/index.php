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
$sessionQuery = 'sessionId=' . rawurlencode($sessionId);
$escape = static function (string $value): string {
    return htmlspecialchars($value, ENT_QUOTES, 'UTF-8');
};

?>
<!DOCTYPE html>
<html lang="<?= $escape($language) ?>">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#101a1d">
    <meta name="description" content="<?= $escape($text['hero_description']) ?>">
    <title>Image → 3D — <?= $escape($text['hero_title']) ?></title>
    <script type="importmap">
    {
        "imports": {
            "three": "https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js",
            "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.180.0/examples/jsm/"
        }
    }
    </script>
    <link rel="stylesheet" href="assets/css/index.css">
    <script src="assets/js/landing.js" defer></script>
</head>
<body class="img3d-page">
    <header class="img3d-header">
        <div class="img3d-header-inner">
            <a class="img3d-brand" href="#top" aria-label="Image to 3D — <?= $escape($text['nav_about']) ?>">
                <span class="img3d-brand-mark" aria-hidden="true"><span></span><span></span><span></span></span>
                <span>Image <i>→</i> 3D</span>
            </a>

            <button class="img3d-menu-toggle" type="button" aria-expanded="false" aria-controls="siteNav"
                    aria-label="<?= $escape($text['menu_open']) ?>"
                    data-nav-open-label="<?= $escape($text['menu_open']) ?>"
                    data-nav-close-label="<?= $escape($text['menu_close']) ?>" data-nav-toggle>
                <span></span><span></span>
            </button>

            <nav class="img3d-nav" id="siteNav" aria-label="<?= $escape($text['footer_navigation']) ?>" data-nav>
                <a href="#about" data-nav-link><?= $escape($text['nav_about']) ?></a>
                <a href="#how-it-works" data-nav-link><?= $escape($text['nav_how']) ?></a>
                <a href="#applications" data-nav-link><?= $escape($text['nav_applications']) ?></a>
                <a href="#roadmap" data-nav-link><?= $escape($text['nav_roadmap']) ?></a>
                <div class="img3d-languages" aria-label="<?= $escape($text['footer_language']) ?>">
                    <a href="?lang=pl&amp;<?= $sessionQuery ?>" lang="pl" hreflang="pl"
                       <?= $language === 'pl' ? 'aria-current="page"' : '' ?>>PL</a>
                    <span aria-hidden="true">/</span>
                    <a href="?lang=en&amp;<?= $sessionQuery ?>" lang="en" hreflang="en"
                       <?= $language === 'en' ? 'aria-current="page"' : '' ?>>EN</a>
                </div>
                <a class="img3d-button img3d-button-small img3d-nav-cta" href="#try"><?= $escape($text['try_app']) ?><span aria-hidden="true">↗</span></a>
            </nav>
        </div>
    </header>

    <main id="top">
        <section class="img3d-hero img3d-section">
            <div class="img3d-hero-grid img3d-shell">
                <div class="img3d-hero-copy img3d-reveal">
                    <p class="img3d-eyebrow"><span></span><?= $escape($text['hero_eyebrow']) ?></p>
                    <h1><?= $escape($text['hero_title']) ?></h1>
                    <p class="img3d-hero-description"><?= $escape($text['hero_description']) ?></p>
                    <div class="img3d-actions">
                        <a class="img3d-button" href="#try"><?= $escape($text['hero_primary']) ?><span aria-hidden="true">↗</span></a>
                        <a class="img3d-text-link" href="#how-it-works"><?= $escape($text['hero_secondary']) ?><span aria-hidden="true">↓</span></a>
                    </div>
                    <p class="img3d-hero-note"><span aria-hidden="true">◈</span> <?= $escape($text['concept_visual']) ?></p>
                </div>

                <div class="img3d-hero-visual img3d-reveal" aria-label="<?= $escape($text['concept_visual']) ?>">
                    <div class="img3d-visual-topline"><span>IMAGE / GEOMETRY</span><span>01—03</span></div>
                    <svg class="img3d-architecture" viewBox="0 0 720 540" role="img" aria-labelledby="heroVisualTitle">
                        <title id="heroVisualTitle"><?= $escape($text['concept_visual']) ?></title>
                        <defs>
                            <linearGradient id="img3dFacade" x1="0" x2="1" y1="0" y2="1">
                                <stop offset="0" stop-color="#45635e"/>
                                <stop offset="1" stop-color="#1b302f"/>
                            </linearGradient>
                            <linearGradient id="img3dSide" x1="0" x2="1" y1="0" y2="1">
                                <stop offset="0" stop-color="#b4c2a5"/>
                                <stop offset="1" stop-color="#667c70"/>
                            </linearGradient>
                            <pattern id="img3dGrid" width="28" height="28" patternUnits="userSpaceOnUse">
                                <path d="M28 0H0V28" fill="none" stroke="#c7d5c5" stroke-opacity=".12"/>
                            </pattern>
                        </defs>
                        <rect width="720" height="540" rx="18" fill="#142225"/>
                        <rect width="720" height="540" rx="18" fill="url(#img3dGrid)"/>
                        <circle cx="550" cy="115" r="110" fill="#c7d5c5" opacity=".05"/>
                        <path d="M48 433H673" stroke="#9cb4a4" stroke-opacity=".3"/>
                        <g class="img3d-blueprint" fill="none" stroke="#d0ddc9" stroke-opacity=".25">
                            <path d="M62 375 180 308l119 67-118 70z"/>
                            <path d="M180 308v137m119-70v-70"/>
                            <path d="m62 375 118 69 119-69"/>
                            <path d="M92 357v65m30-83v66m29-83v66m31-50v67m31-51v67m31-50v66"/>
                        </g>
                        <g class="img3d-building">
                            <path d="m320 270 156-90 154 90v162H320z" fill="url(#img3dFacade)" stroke="#dce6d5" stroke-opacity=".56"/>
                            <path d="m476 180 154 90v162l-154-91z" fill="url(#img3dSide)" stroke="#dce6d5" stroke-opacity=".66"/>
                            <path d="m320 270 156-92 154 91-154 91z" fill="#d6dfc9" fill-opacity=".18" stroke="#e2eadc" stroke-opacity=".75"/>
                            <path d="m346 278 129-75v130l-129 75z" fill="#192b2d" stroke="#d7e1d2" stroke-opacity=".35"/>
                            <path d="m500 208 103 60v127l-103-61z" fill="#233a39" stroke="#e0e8d7" stroke-opacity=".55"/>
                            <path d="m345 328 130-76m-130 101 130-76m-130 101 130-76" stroke="#d5e0d3" stroke-opacity=".3"/>
                            <path d="m500 264 102 59m-102-32 102 59m-102-32 102 59m-102-32 102 59" stroke="#e4eadc" stroke-opacity=".38"/>
                            <path d="M476 180v182m154-92-154 92m-156-92 156 92 154-92" fill="none" stroke="#f0f3e9" stroke-opacity=".78"/>
                            <path d="m318 270 158-93 156 91" fill="none" stroke="#d7e6d6" stroke-width="2" stroke-dasharray="5 8"/>
                        </g>
                        <g class="img3d-point" fill="#d1e3b2">
                            <circle cx="320" cy="270" r="4"/><circle cx="476" cy="180" r="4"/>
                            <circle cx="630" cy="270" r="4"/><circle cx="476" cy="361" r="4"/>
                        </g>
                        <g fill="#dce7d8" font-family="monospace" font-size="11" letter-spacing="1.4">
                            <text x="48" y="48"><?= $escape($text['visual_input']) ?></text>
                            <text x="269" y="48"><?= $escape($text['visual_planes']) ?></text>
                            <text x="507" y="48"><?= $escape($text['visual_model']) ?></text>
                        </g>
                        <path d="M205 42h44m-5-5 5 5-5 5M444 42h44m-5-5 5 5-5 5" fill="none" stroke="#c8dbab" stroke-width="1.5"/>
                        <g fill="#cbd8c5" font-family="monospace" font-size="10" opacity=".7">
                            <text x="556" y="466">X  12.480</text><text x="556" y="484">Y   8.225</text><text x="556" y="502">Z   6.100</text>
                            <text x="53" y="490">CONCEPT / 3D RECONSTRUCTION</text>
                        </g>
                    </svg>
                    <div class="img3d-visual-caption"><span class="img3d-status-dot"></span><?= $escape($text['concept_visual']) ?></div>
                </div>
            </div>
            <div class="img3d-hero-baseline img3d-shell"><span>01 — IMAGE</span><span>02 — PLANES</span><span>03 — GEOMETRY</span><span>EXPERIMENTAL SYSTEM</span></div>
        </section>

        <section class="img3d-about img3d-section" id="about">
            <div class="img3d-shell img3d-about-grid">
                <div class="img3d-about-copy img3d-reveal">
                    <p class="img3d-eyebrow"><?= $escape($text['about_eyebrow']) ?> <span> / 01</span></p>
                    <h2><?= $escape($text['about_title']) ?></h2>
                    <p class="img3d-lead"><?= $escape($text['about_lead']) ?></p>
                    <p class="img3d-body-copy"><?= $escape($text['about_body']) ?></p>
                    <a class="img3d-inline-link" href="#how-it-works"><?= $escape($text['hero_secondary']) ?><span aria-hidden="true">↗</span></a>
                </div>
                <div class="img3d-facts img3d-reveal">
                    <div class="img3d-fact"><span>01</span><p><?= $escape($text['fact_single_photo']) ?></p><b aria-hidden="true">↗</b></div>
                    <div class="img3d-fact"><span>02</span><p><?= $escape($text['fact_planes']) ?></p><b aria-hidden="true">⌗</b></div>
                    <div class="img3d-fact"><span>03</span><p><?= $escape($text['fact_geometry']) ?></p><b aria-hidden="true">◇</b></div>
                    <div class="img3d-fact"><span>04</span><p><?= $escape($text['fact_glb']) ?></p><b aria-hidden="true">↓</b></div>
                </div>
            </div>
        </section>

        <section class="img3d-process img3d-section" id="how-it-works">
            <div class="img3d-shell">
                <div class="img3d-section-heading img3d-reveal">
                    <div><p class="img3d-eyebrow"><?= $escape($text['how_eyebrow']) ?> <span> / 02</span></p><h2><?= $escape($text['how_title']) ?></h2></div>
                    <p><?= $escape($text['how_description']) ?></p>
                </div>
                <div class="img3d-steps">
                    <?php foreach ($text['steps'] as $index => $step): ?>
                    <article class="img3d-step img3d-reveal">
                        <div class="img3d-step-visual img3d-step-visual-<?= $index + 1 ?>">
                            <span class="img3d-step-number">0<?= $index + 1 ?></span>
                            <?php if ($index === 0): ?>
                                <svg viewBox="0 0 180 110" aria-hidden="true"><rect x="26" y="14" width="128" height="82" rx="5"/><path d="m37 80 30-31 19 17 19-26 38 40"/><circle cx="115" cy="34" r="7"/></svg>
                            <?php elseif ($index === 1): ?>
                                <svg viewBox="0 0 180 110" aria-hidden="true"><path d="m28 78 62-46 62 46-62 30z"/><path d="M28 78v-32l62-35 62 35v32M90 32v76"/><path d="m46 66 44-26 45 26M46 75l44-26 45 26"/></svg>
                            <?php elseif ($index === 2): ?>
                                <svg viewBox="0 0 180 110" aria-hidden="true"><path d="m43 43 47-28 47 28v52H43z"/><path d="m90 15 47 28-47 28-47-28M90 71v24m-47-52 47 28 47-28"/></svg>
                            <?php else: ?>
                                <svg viewBox="0 0 180 110" aria-hidden="true"><path d="M48 22h54l28 28v38H48z"/><path d="M102 22v29h28M90 46v43m-17-17 17 17 17-17"/></svg>
                            <?php endif; ?>
                            <span class="img3d-step-scan"></span>
                        </div>
                        <h3><?= $escape($step['title']) ?></h3>
                        <p><?= $escape($step['body']) ?></p>
                    </article>
                    <?php endforeach; ?>
                </div>
            </div>
        </section>

        <section class="img3d-tool-section img3d-section" id="try">
            <div class="img3d-shell">
                <div class="img3d-section-heading img3d-tool-heading img3d-reveal">
                    <div><p class="img3d-eyebrow"><?= $escape($text['app_eyebrow']) ?> <span> / 03</span></p><h2><?= $escape($text['app_title']) ?></h2></div>
                    <p><?= $escape($text['app_description']) ?></p>
                </div>

                <section class="img3d-tool img3d-reveal" aria-label="<?= $escape($text['app_title']) ?>">
                    <div class="img3d-tool-topbar">
                        <div class="img3d-tool-title"><span class="img3d-tool-icon" aria-hidden="true">◈</span><div><strong>Image → 3D</strong><span><?= $escape($text['app_session']) ?></span></div></div>
                        <div class="img3d-tool-lights" aria-hidden="true"><i></i><i></i><i></i></div>
                    </div>
                    <div class="img3d-tool-content">
                        <div class="img3d-tool-controls">
                            <div class="img3d-tool-intro"><span>01 / INPUT</span><p><?= $escape($text['upload_photo']) ?></p></div>
                            <div class="img3d-session-info session-info">
                                <div><span class="label"><?= $escape($text['session_id']) ?></span> <span id="sessionId"></span></div>
                                <div><span class="label"><?= $escape($text['created']) ?></span> <span id="createdOn"></span></div>
                            </div>
                            <div class="upload-section">
                                <div class="upload-buttons">
                                    <input type="file" id="photoInput" accept="image/jpeg,image/png,image/webp">
                                    <label for="photoInput" class="button" id="uploadButton" hidden><?= $escape($text['upload_photo']) ?></label>
                                    <button type="button" class="button new-session" id="newSessionButton"><?= $escape($text['new_session']) ?></button>
                                    <button type="button" class="button download-model" id="downloadModelButton" hidden><?= $escape($text['download_model']) ?></button>
                                </div>
                                <div class="filename" id="filename"></div>
                                <div class="image-preview" id="imagePreviewWrapper">
                                    <img id="imagePreview" alt="<?= $escape($text['image_preview']) ?>">
                                </div>
                            </div>
                            <section class="status" id="status-container" aria-live="polite">
                                <div class="img3d-status-label"><strong><?= $escape($text['status_label']) ?></strong><span id="statusText"><?= $escape($text['waiting']) ?></span></div>
                                <div class="progress-container"><div class="progress-bar" id="progressBar"></div></div>
                                <div class="progress-text" id="progressText">0%</div>
                            </section>
                            <div class="error" id="errorBox" role="alert"></div>
                            <p class="img3d-tool-footnote"><span aria-hidden="true">⌁</span><?= $escape($text['best_results']) ?></p>
                        </div>
                        <div class="img3d-tool-output">
                            <div class="img3d-output-heading"><span>02 / OUTPUT</span><span>GLB · 3D VIEW</span></div>
                            <div id="viewer"><div class="viewer-message"><?= $escape($text['viewer_placeholder']) ?></div></div>
                        </div>
                    </div>
                </section>
            </div>
        </section>

        <section class="img3d-applications img3d-section" id="applications">
            <div class="img3d-shell">
                <div class="img3d-section-heading img3d-reveal">
                    <div><p class="img3d-eyebrow"><?= $escape($text['applications_eyebrow']) ?> <span> / 04</span></p><h2><?= $escape($text['applications_title']) ?></h2></div>
                </div>
                <div class="img3d-capability-grid">
                    <article class="img3d-capability img3d-capability-current img3d-reveal">
                        <div class="img3d-capability-art" aria-hidden="true"><span class="img3d-capability-axis">X</span><span class="img3d-capability-axis">Y</span><span class="img3d-capability-axis">Z</span><div class="img3d-wire-cube"><i></i><i></i><i></i><i></i></div><span class="img3d-capability-tag">CURRENT / APP</span></div>
                        <div class="img3d-capability-copy"><p class="img3d-eyebrow"><?= $escape($text['current_capabilities']) ?></p><p><?= $escape($text['current_capabilities_body']) ?></p><a class="img3d-inline-link" href="#try"><?= $escape($text['hero_primary']) ?><span aria-hidden="true">↗</span></a></div>
                    </article>
                    <article class="img3d-capability img3d-capability-future img3d-reveal">
                        <div class="img3d-capability-copy"><p class="img3d-eyebrow"><?= $escape($text['potential_uses']) ?></p><p class="img3d-potential-note"><?= $escape($text['potential_note']) ?></p>
                            <ul class="img3d-check-list">
                                <?php foreach ($text['potential_items'] as $item): ?>
                                <li><span aria-hidden="true">↗</span><?= $escape($item) ?></li>
                                <?php endforeach; ?>
                            </ul>
                        </div>
                        <div class="img3d-capability-art img3d-capability-art-future" aria-hidden="true"><div class="img3d-orbit img3d-orbit-one"></div><div class="img3d-orbit img3d-orbit-two"></div><div class="img3d-orbit-core">3D</div><span class="img3d-capability-tag">EXPLORATION / FUTURE</span></div>
                    </article>
                </div>
            </div>
        </section>

        <section class="img3d-roadmap img3d-section" id="roadmap">
            <div class="img3d-shell img3d-roadmap-grid">
                <div class="img3d-roadmap-intro img3d-reveal">
                    <p class="img3d-eyebrow"><?= $escape($text['roadmap_eyebrow']) ?> <span> / 05</span></p>
                    <h2><?= $escape($text['roadmap_title']) ?></h2>
                    <p><?= $escape($text['roadmap_description']) ?></p>
                </div>
                <ol class="img3d-roadmap-list">
                    <?php foreach ($text['roadmap_items'] as $index => $item): ?>
                    <li class="img3d-reveal"><span>0<?= $index + 1 ?></span><p><?= $escape($item) ?></p><b aria-hidden="true">↗</b></li>
                    <?php endforeach; ?>
                </ol>
            </div>
        </section>

        <section class="img3d-cta-section img3d-section">
            <div class="img3d-shell">
                <div class="img3d-cta-panel img3d-reveal">
                    <div><p class="img3d-eyebrow"><?= $escape($text['closing_eyebrow']) ?></p><h2><?= $escape($text['closing_title']) ?></h2><p><?= $escape($text['closing_description']) ?></p></div>
                    <a class="img3d-button img3d-button-light" href="#try"><?= $escape($text['closing_cta']) ?><span aria-hidden="true">↗</span></a>
                    <div class="img3d-cta-orb" aria-hidden="true"></div>
                </div>
            </div>
        </section>
    </main>

    <footer class="img3d-footer">
        <div class="img3d-shell">
            <div class="img3d-footer-main">
                <div><a class="img3d-brand" href="#top"><span class="img3d-brand-mark" aria-hidden="true"><span></span><span></span><span></span></span><span>Image <i>→</i> 3D</span></a><p><?= $escape($text['footer_description']) ?></p></div>
                <div class="img3d-footer-links"><strong><?= $escape($text['footer_navigation']) ?></strong><a href="#about"><?= $escape($text['nav_about']) ?></a><a href="#how-it-works"><?= $escape($text['nav_how']) ?></a><a href="#applications"><?= $escape($text['nav_applications']) ?></a><a href="#roadmap"><?= $escape($text['nav_roadmap']) ?></a><a href="#try"><?= $escape($text['try_app']) ?></a><a href="multiphoto.php">Tryb wielozdjęciowy (dev)</a></div>
                <div class="img3d-footer-links"><strong><?= $escape($text['footer_language']) ?></strong><a href="?lang=pl&amp;<?= $sessionQuery ?>" lang="pl" hreflang="pl">Polski</a><a href="?lang=en&amp;<?= $sessionQuery ?>" lang="en" hreflang="en">English</a></div>
            </div>
            <div class="img3d-footer-bottom"><span>© <?= date('Y') ?> Image → 3D</span><span>AN EXPERIMENTAL COMPUTER VISION PROJECT</span><a href="#top"><?= $escape($text['footer_top'] ?? '↑ Top') ?></a></div>
        </div>
    </footer>

    <script id="img3dConfig" type="application/json"><?= json_encode(
        $clientConfig,
        JSON_UNESCAPED_UNICODE | JSON_HEX_TAG | JSON_HEX_APOS | JSON_HEX_AMP | JSON_HEX_QUOT
    ) ?></script>
    <script type="module" src="assets/js/app.js"></script>
</body>
</html>
