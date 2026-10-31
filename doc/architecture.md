# Architektura projektu 3D From Video

## Cel i aktualny stan

3D From Video jest prototypem systemu przekształcającego dane wizualne w lekkie modele 3D w formacie GLB. Priorytetem jest odtworzenie głównych brył i płaszczyzn, szczególnie elementów architektonicznych, bez generowania ciężkich chmur punktów.

Aktualnie główny przepływ aplikacji obsługuje **pojedyncze zdjęcie → model GLB**. W repozytorium znajdują się również narzędzia do pracy z filmem, klatkami i kalibracją kamery, ale nie są one jeszcze częścią tego samego kompletnego przepływu webowego. Opisana architektura odzwierciedla bieżący kod i nie zakłada, że planowane funkcje wideo są już ukończone.

## Widok systemu

```text
Użytkownik
   │
   ▼
Przeglądarka: PHP + JavaScript + CSS + podgląd Three.js
   │ HTTP: utworzenie sesji, upload, odczyt statusu i GLB
   ▼
PHP: system/web_img3d
   │
   ├── katalog danych: data/{sessionId}/photo.* + state.json
   │
   ▼
Node.js WebSocket: system/img3d_ws
   │ przydział zadania i przesłanie zdjęcia (JSON + dane binarne)
   ▼
Worker Node.js: system/img3d_ws_agent
   │ uruchamianie skryptów Python i raportowanie postępu
   ├── ai_moge3.py: estymacja geometrii/głębi z obrazu
   ├── geom_process.py: ekstrakcja płaszczyzn i prostokątów, tekstury
   └── plik GLB zwracany do serwera WebSocket
   │
   ▼
data/{sessionId}/model.glb + state.json → status.php → viewer
```

W typowym wdrożeniu serwer WWW udostępnia PHP przez HTTPS, a reverse proxy przekazuje połączenia WSS do usługi Node.js. Serwer WebSocket domyślnie nasłuchuje na `127.0.0.1`, więc dostęp z zewnątrz wymaga odpowiedniej konfiguracji proxy.

## Główne komponenty

### Interfejs webowy — `system/web_img3d/`

- `index.php` ładuje tłumaczenia, ogranicza częstotliwość tworzenia sesji, wznawia poprawną sesję albo tworzy nową.
- `includes/session.php` generuje identyfikator sesji jako 32 znaki szesnastkowe i zapisuje początkowy stan.
- `upload.php` przyjmuje zdjęcie metodą POST, sprawdza poprawność obrazu i dozwolony MIME type (JPEG, PNG, WEBP), ogranicza rozmiar do 20 MB i zapisuje je w katalogu sesji.
- `status.php` udostępnia stan sesji przez GET. Gdy stan jest `ready`, sprawdza obecność pliku GLB i zwraca ścieżkę do niego.
- `get-glb.php` i `get-photo.php` udostępniają pliki sesji, a skrypty `assets/js/` obsługują interakcje, status, podgląd zdjęcia i modelu.
- `assets/js/viewer.js` odpowiada za podgląd modelu w przeglądarce.

Interfejs i usługi backendowe współdzielą dane sesji przez katalog `data`. Aplikacja używa stanu plikowego zamiast centralnej bazy danych.

### Usługa WebSocket — `system/img3d_ws/`

- `src/server.js` uruchamia serwer WebSocket, autoryzuje workery i obsługuje ich komunikaty.
- `src/agents.js` przechowuje konfigurację autoryzowanych i podłączonych agentów.
- `src/jobs.js` wyszukuje sesje ze stanem `uploaded`, przypisuje zadanie wolnemu workerowi, aktualizuje `state.json`, zapisuje wynik GLB i obsługuje błędy lub rozłączenia.
- Obserwator plików wykrywa nowe zdjęcia w katalogu danych i inicjuje skanowanie oczekujących zadań. Skanowanie jest również uruchamiane po zdarzeniach związanych z workerami i zadaniami, np. po podłączeniu workera lub zakończeniu zadania.
- Serwer dopuszcza do 200 MB dla payloadu WebSocket; limit uploadu HTTP w PHP wynosi 20 MB.

Po stronie usługi Node.js konfiguracja obejmuje między innymi `DATA_DIR`, `PORT` i `AGENTS_FILE`. Przykładowy model wdrożenia i reverse proxy opisuje `system/img3d_ws/Readme.md`.

### Worker — `system/img3d_ws_agent/`

Worker łączy się z serwerem WSS, uwierzytelnia przy użyciu identyfikatora i tokenu agenta, odbiera opis zadania oraz binarne dane zdjęcia. Obsługuje jednocześnie jedno zadanie na połączenie, zapisuje zdjęcie do katalogu roboczego sesji, uruchamia kolejne etapy, raportuje postęp i wysyła wynik GLB z powrotem do serwera.

W obecnej implementacji główne etapy to przygotowanie pliku, uruchomienie MoGe-3, rekonstrukcja geometrii i odczyt wynikowego GLB. Skrypty Python są uruchamiane jako procesy potomne; kod zakończenia procesu wpływa na powodzenie etapu.

### Pipeline obrazu — `system/py/`

- `ai_moge3.py` uruchamia lokalny model MoGe-3 i zapisuje wyniki inferencji (m.in. punkty, głębię, maskę i normalne) do pliku `moge3.pt`.
- `geom_process.py` używa tych danych do grupowania kierunków normalnych i płaszczyzn, wyznaczania prostokątnych regionów oraz teksturowania ich z obrazu.
- Moduły `geom_*` realizują etapy rekonstrukcji i eksportu. Wyniki pośrednie i debugowe mogą być zapisywane w podkatalogu obrazu.
- Worker oczekuje pliku GLB w podkatalogu obrazu, a następnie przesyła jego zawartość binarną do usługi WebSocket.

Kod inferencji aktualnie wybiera urządzenie CUDA (`DEVICE = "cuda"`), więc dostępność odpowiedniego środowiska GPU i lokalnego modelu jest istotnym warunkiem uruchomienia pipeline.

## Przepływ danych dla zdjęcia

1. Użytkownik otwiera stronę. PHP wznawia istniejącą sesję po prawidłowym `sessionId` albo tworzy nową.
2. Katalog `data/{sessionId}/` otrzymuje początkowy `state.json`, a sesja ma stan oczekiwania.
3. Przeglądarka wysyła zdjęcie do `upload.php`. Po walidacji PHP zapisuje `photo.jpg`, `photo.png` lub `photo.webp` oraz ustawia stan `uploaded`.
4. Obserwator serwera WebSocket wykrywa plik i inicjuje skanowanie oczekujących sesji. Serwer wybiera bezczynnego workera, tworzy `jobId`, zmienia stan sesji na `processing` i wysyła metadane zadania oraz zdjęcie. Skanowanie jest ponawiane również po wybranych zdarzeniach obsługi workerów i zadań.
5. Worker uruchamia pipeline: zapis wejścia, inferencja MoGe-3, rekonstrukcja geometrii i odczyt pliku GLB.
6. Worker raportuje postęp przez komunikaty WebSocket. Serwer zapisuje postęp w `state.json`.
7. Po otrzymaniu GLB serwer sprawdza nagłówek `glTF`, zapisuje wynik jako `model.glb` i ustawia stan `ready` z postępem 100%.
8. Przeglądarka odczytuje stan przez PHP i udostępnia podgląd lub pobranie modelu.

### Kontrakt sesji i zadania

Katalog sesji jest wspólnym punktem wymiany pomiędzy PHP a backendem. Typowe pliki to:

```text
data/{sessionId}/
├── state.json
├── photo.jpg | photo.png | photo.webp
└── model.glb
```

`sessionId` ma format 32 znaków hex. Stan zawiera co najmniej `createdOn`, `status` i `progress`; podczas przetwarzania backend może zapisać również `jobId` i identyfikator workera, a po sukcesie ścieżkę GLB. W praktyce występują statusy oczekiwania, `uploaded`, `processing`, `ready` i `error`; status początkowy interfejsu może być zlokalizowany.

Komunikacja worker–serwer używa komunikatów JSON dla autoryzacji, opisu zadania, postępu i błędów. Zdjęcie oraz końcowy GLB są przesyłane jako osobne wiadomości binarne. Wysyłka GLB jest poprzedzana komunikatem `ready_for_glb`.

## Przetwarzanie wideo — stan obecny

Repozytorium zawiera oddzielny mechanizm oparty na `system/watcher.js` i `system/videoProcessor.js`. Obserwator wykrywa wybrane pliki MP4 w strukturze `users/` i uruchamia zadania kalibracji lub przetwarzania. Kod procesora obejmuje m.in. ekstrakcję klatek przez FFmpeg, korekcję zniekształceń i narzędzia analizy klatek.

To osobna ścieżka pomocnicza, niezintegrowana w kodzie z pełnym webowym cyklem sesji zdjęcia, kolejką WebSocket i dostarczeniem jednego końcowego modelu GLB z wielu klatek. W szczególności wybór klatek, ich wspólna rekonstrukcja, spójność geometrii i końcowy eksport modelu z filmu pozostają kierunkami dalszego rozwoju, a nie gwarantowaną funkcją gotową do użycia.

## Uruchamianie i konfiguracja — ogólnie

Projekt wymaga środowisk odpowiednich dla poszczególnych warstw:

- serwera WWW z PHP dla interfejsu i endpointów;
- Node.js/npm dla głównego projektu, usługi WebSocket i workera (każda usługa ma własny katalog i manifest npm);
- Pythona oraz bibliotek wykorzystywanych przez skrypty `system/py/`;
- lokalnie dostępnego modelu MoGe-3 skonfigurowanego przez `MOGE_MODEL_PATH`;
- CUDA/GPU dla obecnej konfiguracji inferencji MoGe-3;
- wspólnego katalogu danych PHP i usługi WebSocket; worker otrzymuje zdjęcie przez WebSocket i zapisuje je w swoim katalogu roboczym, który może znajdować się na innej maszynie;
- sekretów i konfiguracji połączenia workera przechowywanych poza kodem, np. w środowisku procesu lub pliku `.env`.

Dokładna konfiguracja zależy od środowiska. Szczegóły instalacji usługi WebSocket są w `system/img3d_ws/Readme.md`, a główne założenia projektu w `Readme.md`.

## Granice odpowiedzialności przy rozwoju

- **UI webowe:** sesje użytkownika, upload, status i wizualizacja GLB.
- **Backend Node.js:** uwierzytelnienie workerów, kolejka, transport, postęp i zapis wyniku.
- **Worker:** połączenie z backendem i uruchomienie pipeline jako procesów.
- **Python:** inferencja, analiza obrazu, rekonstrukcja geometrii i eksport modelu.
- **Wideo:** osobna ścieżka wymagająca uzgodnienia kontraktów, jeśli ma zostać włączona do głównego przepływu aplikacji.

Zmiana formatu danych, statusów sesji, ścieżek plików lub komunikatów WebSocket może wymagać jednoczesnej aktualizacji kilku komponentów. Przed takim rozszerzeniem należy sprawdzić aktualnych producentów i konsumentów danego kontraktu.

## Testowanie

Testy i skrypty są rozproszone pomiędzy katalogami. Usługa WebSocket deklaruje test `npm test` w `system/img3d_ws/`. Manifest workera obecnie nie definiuje właściwego zestawu testów — jego skrypt `test` zwraca błąd „no test specified”. W repozytorium istnieją również testy i skrypty Python/JavaScript powiązane z konkretnymi etapami, ale ich uruchomienie może wymagać modeli, GPU, danych testowych lub dodatkowych zależności.

Test jednostkowy pojedynczego modułu nie potwierdza pełnego przebiegu od uploadu do wyświetlenia GLB. Weryfikacja end-to-end wymaga środowiska z PHP, WebSocketem, workerem, modelem i zgodnym katalogiem danych.
