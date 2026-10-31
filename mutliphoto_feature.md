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
