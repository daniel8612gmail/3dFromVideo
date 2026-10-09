<?php

function resolveLanguage(): string
{
    $supportedLanguages = ['pl', 'en'];
    $requestedLanguage = $_GET['lang'] ?? null;

    if (
        is_string($requestedLanguage)
        && in_array($requestedLanguage, $supportedLanguages, true)
    ) {
        setcookie(
            'img3d_lang',
            $requestedLanguage,
            [
                'expires' => time() + 31536000,
                'path' => '/',
                'secure' => !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off',
                'httponly' => true,
                'samesite' => 'Lax'
            ]
        );

        return $requestedLanguage;
    }

    $savedLanguage = $_COOKIE['img3d_lang'] ?? null;

    if (
        is_string($savedLanguage)
        && in_array($savedLanguage, $supportedLanguages, true)
    ) {
        return $savedLanguage;
    }

    $acceptedLanguages = [];
    $header = $_SERVER['HTTP_ACCEPT_LANGUAGE'] ?? '';

    foreach (explode(',', $header) as $position => $entry) {
        $parts = explode(';', trim($entry));
        $locale = strtolower(trim($parts[0]));
        $quality = 1.0;

        if (isset($parts[1]) && preg_match('/^\s*q=([0-9.]+)\s*$/i', $parts[1], $matches)) {
            $quality = (float) $matches[1];
        }

        if ($locale !== '' && $quality > 0) {
            $acceptedLanguages[] = [
                'locale' => $locale,
                'quality' => $quality,
                'position' => $position
            ];
        }
    }

    usort(
        $acceptedLanguages,
        static function (array $left, array $right): int {
            if ($left['quality'] === $right['quality']) {
                return $left['position'] <=> $right['position'];
            }

            return $right['quality'] <=> $left['quality'];
        }
    );

    foreach ($acceptedLanguages as $acceptedLanguage) {
        $localeLanguage = explode('-', $acceptedLanguage['locale'])[0];

        if (in_array($localeLanguage, $supportedLanguages, true)) {
            return $localeLanguage;
        }
    }

    return 'pl';
}

function getTranslations(string $language): array
{
    $translations = [
        'pl' => [
            'description' => 'System przeznaczony do generowania modelu 3D dla elementów architektury z pojedynczego zdjęcia.',
            'description_details' => 'Jego celem jest wyszukanie dominujących płaszczyzn z pominięciem nieregularnych obiektów i stworzenie lekkiego modelu geometrycznego na podstawie odnalezionych płaszczyzn.',
            'session_id' => 'Identyfikator sesji:',
            'created' => 'Utworzono:',
            'upload_photo' => 'Wczytaj zdjęcie z urządzenia',
            'new_session' => 'Nowa sesja',
            'selected_file' => 'Wybrano:',
            'image_preview' => 'Podgląd załadowanego zdjęcia',
            'status_label' => 'Status:',
            'waiting' => 'oczekiwanie',
            'uploading' => 'wysyłanie',
            'uploaded' => 'przesłano',
            'processing' => 'przetwarzanie',
            'ready' => 'gotowe',
            'error' => 'błąd',
            'viewer_placeholder' => 'Podgląd modelu 3D pojawi się tutaj.',
            'invalid_image_type' => 'Nieprawidłowy typ pliku. Wybierz JPG, PNG lub WEBP.',
            'file_too_large' => 'Plik jest za duży. Maksymalny rozmiar to 20 MB.',
            'image_read_error' => 'Nie udało się odczytać obrazu.',
            'photo_restore_error' => 'Nie udało się wczytać wcześniej przesłanego zdjęcia.',
            'uploaded_photo' => 'Przesłane zdjęcie',
            'image_resize_error' => 'Nie udało się przeskalować obrazu.',
            'upload_failed' => 'Upload zdjęcia nie powiódł się.',
            'image_processing_error' => 'Wystąpił błąd podczas przetwarzania zdjęcia.',
            'glb_read_error' => 'Nie udało się odczytać modelu GLB.',
            'glb_download_error' => 'Nie udało się pobrać modelu GLB. Spróbuj ponownie.',
            'session_status_error' => 'Nie udało się pobrać statusu sesji.',
            'model_processing_error' => 'Wystąpił błąd podczas przetwarzania modelu.',
            'rate_title' => 'Za dużo żądań',
            'rate_limit_prefix' => 'Możesz utworzyć maksymalnie',
            'rate_limit_suffix' => 'sesje w ciągu minuty.',
            'retry_prefix' => 'Spróbuj ponownie za około',
            'retry_suffix' => 's.',
            'session_create_error' => 'Nie udało się utworzyć katalogu sesji.',
            'server_errors' => []
        ],
        'en' => [
            'description' => 'Generate a 3D model of architectural elements from a single photograph.',
            'description_details' => 'The system identifies dominant planes while ignoring irregular objects, then creates a lightweight geometric model from the detected planes.',
            'session_id' => 'Session ID:',
            'created' => 'Created:',
            'upload_photo' => 'Choose a photo from your device',
            'new_session' => 'New session',
            'selected_file' => 'Selected:',
            'image_preview' => 'Preview of the uploaded photo',
            'status_label' => 'Status:',
            'waiting' => 'waiting',
            'uploading' => 'uploading',
            'uploaded' => 'uploaded',
            'processing' => 'processing',
            'ready' => 'ready',
            'error' => 'error',
            'viewer_placeholder' => 'The 3D model preview will appear here.',
            'invalid_image_type' => 'Unsupported file type. Choose a JPG, PNG, or WEBP image.',
            'file_too_large' => 'The file is too large. The maximum size is 20 MB.',
            'image_read_error' => 'Could not read the image.',
            'photo_restore_error' => 'Could not load the previously uploaded photo.',
            'uploaded_photo' => 'Uploaded photo',
            'image_resize_error' => 'Could not resize the image.',
            'upload_failed' => 'The photo upload failed.',
            'image_processing_error' => 'An error occurred while processing the photo.',
            'glb_read_error' => 'Could not read the GLB model.',
            'glb_download_error' => 'Could not download the GLB model. Please try again.',
            'session_status_error' => 'Could not retrieve the session status.',
            'model_processing_error' => 'An error occurred while processing the model.',
            'rate_title' => 'Too many requests',
            'rate_limit_prefix' => 'You can create up to',
            'rate_limit_suffix' => 'sessions per minute.',
            'retry_prefix' => 'Please try again in about',
            'retry_suffix' => 's.',
            'session_create_error' => 'Could not create the session directory.',
            'server_errors' => [
                'Dozwolona jest tylko metoda POST.' => 'Only POST requests are allowed.',
                'Nieprawidłowy identyfikator sesji.' => 'Invalid session ID.',
                'Sesja nie istnieje.' => 'The session does not exist.',
                'Nieprawidłowa ścieżka sesji.' => 'Invalid session path.',
                'Nie przesłano zdjęcia.' => 'No photo was uploaded.',
                'Plik przekracza limit serwera.' => 'The file exceeds the server limit.',
                'Plik przekracza dozwolony rozmiar.' => 'The file exceeds the allowed size.',
                'Plik został przesłany tylko częściowo.' => 'The file was only partially uploaded.',
                'Nie przesłano pliku.' => 'No file was uploaded.',
                'Brak katalogu tymczasowego.' => 'The temporary directory is missing.',
                'Nie można zapisać pliku.' => 'The file could not be saved.',
                'Upload został zatrzymany przez rozszerzenie PHP.' => 'The upload was stopped by a PHP extension.',
                'Nieznany błąd uploadu.' => 'Unknown upload error.',
                'Plik jest za duży. Maksymalny rozmiar to 20 MB.' => 'The file is too large. The maximum size is 20 MB.',
                'Nieprawidłowy upload pliku.' => 'Invalid file upload.',
                'Przesłany plik nie jest prawidłowym obrazem.' => 'The uploaded file is not a valid image.',
                'Dozwolone są tylko pliki JPG, PNG i WEBP.' => 'Only JPG, PNG, and WEBP files are allowed.',
                'Zdjęcie zostało już przesłane dla tej sesji.' => 'A photo has already been uploaded for this session.',
                'Nie udało się zapisać zdjęcia.' => 'Could not save the photo.',
                'Nie udało się zapisać stanu sesji.' => 'Could not save the session state.'
            ]
        ]
    ];

    return $translations[$language];
}
