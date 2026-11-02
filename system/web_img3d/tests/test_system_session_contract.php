<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}

require __DIR__ . '/../api/v1/_common.php';

function check(bool $condition, string $message): void
{
    if (!$condition) {
        fwrite(STDERR, "FAIL: $message\n");
        exit(1);
    }
}

$metadata = [
    'frameId' => 'frame_0001',
    'sequence' => 0,
    'timestampMs' => 1780000000123,
    'trackingState' => 'TRACKING',
    'assetId' => 'asset-id',
    'sha256' => str_repeat('a', 64),
    'mimeType' => 'image/jpeg',
    'width' => 1920,
    'height' => 1080,
    'orientation' => 0,
    'imageTransform' => [
        'sourceWidth' => 1920,
        'sourceHeight' => 1080,
        'rotationDegrees' => 0,
        'mirrorX' => false,
        'crop' => ['x' => 0, 'y' => 0, 'width' => 1, 'height' => 1],
    ],
    'arSessionEpochId' => 'epoch-1',
    'referenceFrameId' => 'anchor-1',
    'cameraToFirstFrame' => [
        'translationM' => [0, 0, 0],
        'rotationQuaternionXyzw' => [0, 0, 0, 1],
    ],
    'intrinsics' => ['fx' => 1000, 'fy' => 1000, 'cx' => 960, 'cy' => 540, 'calibrationSource' => 'capture'],
    'distortionStatus' => 'not_provided',
    'cameraProfile' => ['cameraId' => 'camera-a', 'imageWidth' => 1920],
    'exposureDurationNs' => 12500000,
];

$validated = validateFrameMetadata($metadata, 1920, 1080, 'image/jpeg');
check($validated['frameId'] === 'frame_0001', 'accepts a complete valid frame contract');
check($validated === $metadata, 'preserves all capture metadata, including arbitrary capture extensions');
check(!array_key_exists('systemSessionId', $validated), 'keeps systemSessionId separate from frame metadata');
check(array_key_exists('cameraToFirstFrame', $validated), 'requires explicit logical scan pose metadata');
foreach (['mogeToCameraMatrix4x4', 'scaleEstimate', 'axes'] as $modelField) {
    check(!array_key_exists($modelField, $validated), "does not require client model convention field $modelField");
}
check(validId($metadata['frameId'], SYSTEM_FRAME_ID_PATTERN), 'accepts safe frame IDs');
check(!validId('../outside', SYSTEM_FRAME_ID_PATTERN), 'rejects path traversal frame IDs');

$canonical = canonicalJson($metadata);
$reordered = $metadata;
$reordered['intrinsics'] = array_reverse($reordered['intrinsics'], true);
check($canonical === canonicalJson($reordered), 'canonical metadata ignores JSON object key order');
$existing = ['sha256' => str_repeat('a', 64), 'metadataCanonical' => $canonical];
check(sameFrameContent($existing, str_repeat('a', 64), $canonical), 'identical bytes and metadata are idempotent');
check(!sameFrameContent($existing, str_repeat('b', 64), $canonical), 'changed image content is not idempotent');
check(!sameFrameContent($existing, str_repeat('a', 64), $canonical . ' '), 'changed metadata is not idempotent');

echo "PHP system-session contract tests passed.\n";
