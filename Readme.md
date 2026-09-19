# 3D From Video

Projekt z obszaru generowania modeli 3D z danych wizualnych. Umożliwia przygotowanie modelu GLB na podstawie pojedynczego zdjęcia. 

Tworzone modele 3D mają być możliwie proste i lekkie z zachowaniem płaszczyzn i pominięciem małych nieistotnych elementów oraz skomplikowanych kształtów, tak aby odtworzyć elementy architektury i główne elementy otaczającego świata.

Działanie systemu można sprawdzić na https://img3d.pcmagic.pl

## Status projektu

- Obecny tryb: generowanie modelu GLB ze zdjęcia
- Plan rozwoju: generowanie modelu GLB z filmu
- Główne obszary: front-end webowy, połączenie z agentem AI, pipeline przygotowania geometrii i eksportu GLB

W kolejnej fazie rozwoju planowane jest rozszerzenie działania na materiał wideo, gdzie klatki będą analizowane sekwencyjnie i łączone w spójny model 3D. 

## Cel projektu

Celem projektu jest stworzenie kompletnego systemu do tworzenia modeli 3D o małym rozmiarze, które możn a będzie załadować na dużej liczbie urządzeń, w przeciwieństwie do popularnych chmór punktów.

- wykrywania obiektów i geometrii z obrazu,
- przygotowywania danych wejściowych dla modeli 3D,
- budowy prostych modeli geometrycznych,
- eksportu wyników do formatu GLB gotowego do wykorzystania w przeglądarkach, wizualizacjach i aplikacjach webowych.

## Główna architektura

Projekt składa się z kilku warstw:

1. Frontend webowy
   - katalog: system/web_img3d
   - odpowiada za upload zdjęcia, obsługę sesji, wyświetlanie stanu przetwarzania i podgląd wynikowego GLB
   - wykorzystuje PHP oraz skrypty frontendowe z podglądem Three.js

2. Warstwa komunikacyjna / WebSocket
   - katalog: system/img3d_ws
   - odpowiada za odbieranie zadań z front-endu, koordynację sesji, wysyłanie zdjęć do agenta AI oraz odbieranie wynikowego pliku GLB
   - zarządza stanem sesji, postępem przetwarzania i kolejką zadań

3. Agent AI / przetwarzanie
   - katalog: system/img3d_ws_agent
   - agent odbiera zadania z serwera WebSocket,
   - pobiera zdjęcie, uruchamia pipeline przetwarzania Python,
   - eksportuje wynik w formacie GLB i zwraca go do systemu centralnego

4. Pipeline obróbki i AI
   - katalog: system/py
   - zawiera skrypty do detekcji, mapowania geometrii, kalibracji, ekstrakcji konturów, przetwarzania mask, budowy płaszczyzn i eksportu modeli 3D

5. Procesy pomocnicze i systemowe
   - katalog: system
   - zawiera watchery, kalibrację, przetwarzanie wideo i mechanizmy uruchamiania aplikacji

## Obecny workflow działania

Aktualnie system działa w następującym cyklu:

1. Użytkownik przesyła zdjęcie przez frontend z katalogu system/web_img3d.
2. PHP tworzy sesję i zapisuje stan w katalogu sesji.
3. Serwer WebSocket z system/img3d_ws sprawdza oczekujące zadania i przydziela je wolnemu agentowi.
4. Agent z system/img3d_ws_agent odbiera zdjęcie i uruchamia pipeline Python.
5. Pipeline przygotowuje dane 3D, tworzy geometrię i eksportuje poprawny plik GLB.
6. Plik GLB jest zapisany w katalogu sesji i dostępny dla frontendowego podglądu.
7. Stan sesji i postęp operacji są odświeżane w czasie rzeczywistym.

To jest obecnie funkcjonalna wersja beta i można ją traktować jako działający prototyp produktów typu Image-to-3D.

## Katalogi projektu

```text
3dFromVideo/
├── package.json
├── Readme.md
├── system/
│   ├── index.js
│   ├── watcher.js
│   ├── videoProcessor.js
│   ├── web_img3d/               # frontend aplikacji
│   ├── img3d_ws/                # serwer WebSocket + job orchestration
│   ├── img3d_ws_agent/          # agent AI po stronie wykonawczej
│   ├── py/                      # skrypty AI / geometry / GLB export
│   ├── calibration/
│   └── ...
├── users/
├── test/
├── yolo26n.pt
├── yolo26n-seg.pt
└── ...
```

## Główne moduły

### Frontend

Katalog system/web_img3d obejmuje warstwę użytkownika:

- upload zdjęć,
- tworzenie sesji,
- kontrola statusu,
- odczyt i prezentacja modelu GLB,
- odświeżanie stanu w czasie pracy.

### WebSocket / orchestration

Katalog system/img3d_ws odpowiada za:

- autoryzację agentów,
- odbieranie zadań z UI,
- przydzielanie pracy odpowiedniemu agentowi,
- monitorowanie statusu sesji,
- odbiór danych binarnych i plików GLB,
- zapis końcowego wyniku do katalogu sesji.

### Agent AI
Agent jest to program przetwarzający zdjęcia. Odbiera zdjęcia z serwera. Działa w kilku etapach i przekazuje wykonany przez siebie model 3D na serwer. Może być uruchomiony na dowolnej maszynie z odpowiednią mocą obliczeniową dla modeli AI. Obecnie używa modelu sztucznej inteligencji MoGe-3 w celu wydobycia głębi i informacji o kierunku każdego z piksela obrazu.

Katalog system/img3d_ws_agent realizuje połączenie z serwerem i uruchamianie pipeline:

- nawiązuje połączenie WebSocket,
- odbiera zadania,
- pobiera zdjęcie od serwera,
- uruchamia skrypty z katalogu system/py,
- wysyła postęp wykonania,
- zwraca wynik GLB do serwera.

#### Instalacja
1. w katalogu img3d_ws_agent uruchom:
``` text
npm install
```

2. Zainstaluj Visual Studio Build Tools for C++ https://visualstudio.microsoft.com/visual-cpp-build-tools/
   Uruchom pobrany instalator.
   W zakładce Workloads zaznacz:
   - Desktop development with C++
   czyli Programowanie aplikacji klasycznych w języku C++.

   - Po prawej stronie upewnij się, że zaznaczone są przynajmniej:
      
      - MSVC v143 - VS 2022 C++ x64/x86 build tools
      - Windows 11 SDK albo Windows 10 SDK
      - C++ CMake tools for Windows 
3. Zainstaluj MoGe-3: https://github.com/microsoft/MoGe

   Na chwilę pisania dokumentacji są to komendy:
   ``` text
   pip install git+https://github.com/microsoft/MoGe.git
   ```
4. Ustawienie Ścieżki do modelu Moge-3:
``` text
przykład dla CMD:
set MOGE_MODEL_PATH=D:\AI3d\models\moge-3-vitl.pt

przykład dls PS
$env:MOGE_MODEL_PATH="C:\AI\model\moge-3-vitl.pt"
(działa do zamknięcia konsoli)
```
Po zmianie konieczny restart terminala

5. Zainstaluj: py torch

### Python pipeline

W katalogu system/py znajdują się narzędzia odpowiedzialne za:

- kalibrację kamery,
- detekcję krawędzi i regionów,
- segmentację i maskowanie,
- budowę geometrii,
- tworzenie płaszczyzn i granic,
- łączenie elementów w strukturę 3D,
- eksport do formatu GLB.

## Aktualne możliwości

W obecnym etapie działania projekt pozwala na:

- dodanie zdjęcia do systemu,
- zainicjowanie sesji przetwarzania,
- uruchomienie agenta AI,
- przygotowanie geometrycznego modelu 3D,
- zapis i odczyt wyniku w formacie GLB,
- pracy w trybie beta z prostym, działającym flow od zdjęcia do modelu 3D.

## Główne wymagania

Do uruchomienia projektu potrzebne są:

- Node.js
- npm
- Python 3
- Model AI MoGe-3
- biblioteki Python używane przez skrypty z katalogu system/py
- serwer web / proxy / WebSocket (w zależności od środowiska wdrożeniowego)
- odpowiednia konfiguracja agentów i tokenów dostępu

## Uruchomienie

W katalogu głównym projektu:

```bash
npm install
npm start
```

To uruchamia główny system, który obserwuje zmiany i inicjuje procesy przetwarzania.

W przypadku uruchamiania usług WebSocket / agentów należy pracować z katalogami:

- system/img3d_ws
- system/img3d_ws_agent

oraz odpowiednimi konfiguracjami środowiskowymi i tokenami.

## Przyszły plan rozwoju

Najważniejszym kierunkiem rozwoju jest przejście z generowania modelu z pojedynczego zdjęcia na generowanie modelu z filmu.

Planowane etapy:

1. wybór klatek z materiału wideo,
2. analiza sekwencji i kalibracja kamery,
3. dopasowanie punktów / geometrii między klatkami,
4. łączenie danych z wielu ujęć w jedną strukturę 3D,
5. poprawa jakości modelu i stabilności pipeline,
6. finalizacja eksportu do GLB z większą dokładnością i lepszą spójnością geometrii.

### Warto zwrócić uwagę

- obecnie projekt jest gotowy do pracy w wersji beta,
- system ma już kompletne elementy do obsługi zdjęć,
- architektura jest przygotowana do rozszerzenia na wideo,
- przyszłe prace koncentrować będą się na sekwencyjnym przetwarzaniu klatek i scalaniu danych 3D.

## Podsumowanie

To repozytorium jest prototypem systemu do generowania modeli 3D z obrazów i filmów. W obecnym stanie działa jako działająca wersja beta służąca do generowania GLB z pojedynczego zdjęcia. Rozwój będzie kontynuowany w kierunku pełnego modelu z filmu, z wykorzystaniem istniejącej architektury front-end + WebSocket + agent AI + pipeline Python.

## Licencja

Projekt korzysta z licencji określonej w pliku package.json / repozytorium i może być rozwijany dalej w ramach dalszej pracy nad systemem 3D.
