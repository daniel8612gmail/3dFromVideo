## Dodanie nowej funkcjonalności
obsługa wielu obrazów dla jednej sesji.
Celem jest dodanie do projektu możliwości obsługi wielu zdjęć w jednej sesji.
Zdjęcia będą wrzucane przez aplikację ze systemem Android, która będzie miała połączenie Ze stroną www - interfejsem. Aplikacja po rozpoczęciu. Działania będzie zbierał obrazy z urządzenia. I dostarczała je. Jeden po drugim wraz z pozycją kamery, w jakiej zostało zdjęcie wykonane. Aplikacja na Androida jest poza zakresem tego zadania.

## Cel
Celem zadania jest:
1. stworzenie interfejsu dla aplikacji Android abym mogła rozpoczynać sesję, a następnie do sesji dodawać zdjęcia wraz z pozycją kamer dla danego zdjęcia.
2. Dodane zdjęcia do sesji powinny być analogicznie do obecnej funkcjonalności przerabiane przez agentów i generowane na ich podstawie Modele 3D.
3. Modele dla jednej sesji powinny być scalane w jeden plik glb. Płaszczyzny w pliku powinny być również scalane, Aby zapobiec duplikatem. To samo dotyczy tekstur - powinny być sumowane i dostosowane do zsumowanej geometrii płaszczyzny.
4. Dla każdej sesji system powinien występować możliwy do odczytu postęp przetwarzania zdjęć. Po każdym przerobionym zdjęcii system powinien dostarczyć dotychczasowy model na serwer, aplikacja android będzie mogła pobrać ten model i Na żywo wyświetlać.


## Propozycja architektoniczna
Jako propozycję podaje wykorzystanie obecnego agenta do generowania modelu 3D dla pojedynczego zdjęcia. Który będzie uruchamiany na wielu urządzeniach jednocześnie. Każde z urządzeń będzie dostawało pojedyncze zdjęcie. 
Na serwerze www zdjecia będą gromadzone dla sesji wraz z wynikami przerabiania zdjęć przez agentów.
Należy dorobić do tego mechanizm "Sumatora", który będzie zbierał wyniki przerabiania każdego ze zdjęć i zcalł to w jeden model docelowy. "Sumator" powinien być również w formie agenta podobnie jak agenci do przerabiania pojedynczych zdjęć.
Zaproponowalem osobnego agenta do scalania klatek w jeden GLB. Bez nowego procesu nie bedzie mozliwosci dzialania na wielu klatkach jednoczesnie. Agenci przerabiajacy pojedyncza klatke dostarczaja GLB z danej klatki. Sumator jako osobny proces powinien zadziałać w momencie otrzymania kolejnego GLB z klatki. Dzięki temu system będzie podzielony na logiczne całości: img-to-GLB jako jedna część całego flow, sumoawnie GLB jako kolejna część uruchamiana po przeprocesowaniu dowolnej klatki. Czyli podobnie jak obecnie istnieje agent uruchamiany na dodanie klatki do systemu i ruruchamia przerabianie klatki na GLB tak nowy flow powinien wygenerowany GLB połączyć do main GLB sumując geometrię i textury i usuwając duplikaty a podobne płaszczyzny łącząc w jedną. Pierwsza klatka może nie zawierać położenia kamery i możemy uznać że jest w położeniu 0. Kolejne klatki są z podanym położeniem względem pierwszej klatki, więc agent img-to-GLB dostarczy GLB. Które w następnym kroku trzeba przesunąć względem pierwszej klatki i dokonać ich scalenia ze sceną już instniejącą zsumowaną z poprzednich klatek. 
Proponuję w ogóle nie rószać agenta img-to-GLB.
Sumator powinien uwzględniać nie tylko położenie kolejnych klatek względem pierwszej, ale również kąt kamery. Rejestracja w aplikacji android jest wykonywana z ręki, pozycja kamery i jej obrót względem pierwszej klatki jest dostarczany przez ARCore.