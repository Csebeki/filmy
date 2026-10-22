# Lista filmów do obejrzenia

Projekt z przedmiotu *Bezpieczeństwo procesów CI/CD*. Aplikacja webowa (Flask + PostgreSQL) wdrażana w Kubernetes razem z Gitea, ArgoCD i TLS z własnego CA.
Autor: Kacper Gajak

## Struktura repozytorium

```
filmy/
├── app/                  # aplikacja
│   ├── app.py            # Flask: lista, dodawanie, edycja, usuwanie, filtry, /healthz, /readyz
│   ├── templates/        # widoki HTML (Bootstrap)
│   ├── requirements.txt
│   └── Dockerfile        # obraz z wersją (APP_VERSION), uruchamiany jako nie-root
├── docker-compose.yml    # tylko do lokalnego testu aplikacji
└── k8s/                  # manifesty Kubernetes (kolejny etap)
```

Aplikacja czyta konfigurację ze zmiennych środowiskowych. W Kubernetes będą pochodzić z ConfigMap i Secret.

| Zmienna | Skąd w K8s | Opis |
| --- | --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER` | ConfigMap | adres i nazwa bazy |
| `DB_PASSWORD` | Secret | hasło do bazy |
| `SECRET_KEY` | Secret | klucz sesji Flask |
| `APP_VERSION` | obraz (build arg) | wersja widoczna w stopce, np. `v1`, `v2` |

Stopka strony pokazuje wersję aplikacji i nazwę poda. Przydaje się w testach 3–5 (odporność, aktualizacja, rollback).

---

# Etap 1: aplikacja (instrukcja krok po kroku, Windows)

Wszystkie polecenia wpisujesz w **PowerShell**.

## Krok 1. Zainstaluj narzędzia

```powershell
winget install Docker.DockerDesktop
winget install Git.Git
winget install Kubernetes.kubectl
winget install Helm.Helm
```

Po instalacji Docker Desktop **zrestartuj komputer**. Przy pierwszym uruchomieniu Docker Desktop może poprosić o włączenie WSL2. Zgódź się albo wpisz w PowerShell jako administrator `wsl --install` i zrestartuj ponownie.

Sprawdź, czy wszystko działa (otwórz **nowe** okno PowerShell):

```powershell
docker version
git --version
kubectl version --client
helm version
```

Załóż darmowe konto na https://hub.docker.com. Twój login to dalej `TWOJ_LOGIN`.

## Krok 2. Rozpakuj projekt

Rozpakuj `filmy.zip` np. do `C:\projekty\filmy` i wejdź do folderu:

```powershell
cd C:\projekty\filmy
```

## Krok 3. Przetestuj aplikację lokalnie (bez Kubernetesa)

```powershell
docker compose up --build
```

Otwórz http://localhost:8000. Dodaj 2–3 filmy, oznacz jeden jako obejrzany, sprawdź filtry i edycję. W stopce powinno być `Wersja aplikacji: v1`.

Zatrzymanie: `Ctrl+C`, potem `docker compose down -v` (`-v` usuwa testowe dane).

## Krok 4. Zbuduj obrazy v1 i v2 i wyślij je do Docker Hub

Od razu budujesz dwie wersje. `v2` przyda się w testach aktualizacji i rollbacku.

```powershell
docker login
docker build -t TWOJ_LOGIN/filmy:v1 --build-arg APP_VERSION=v1 ./app
docker build -t TWOJ_LOGIN/filmy:v2 --build-arg APP_VERSION=v2 ./app
docker push TWOJ_LOGIN/filmy:v1
docker push TWOJ_LOGIN/filmy:v2
```

Na https://hub.docker.com powinno być repozytorium `filmy` z tagami `v1` i `v2`. Musi być **publiczne** (domyślnie jest), wtedy klaster pobierze obraz bez logowania.

Opcjonalnie, plus za bezpieczeństwo: skan podatności obrazu Trivy. Zrób zrzut ekranu wyniku do sprawozdania.

```powershell
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy image TWOJ_LOGIN/filmy:v1
```

## Krok 5. Wrzuć kod na GitHub

Na https://github.com/new utwórz puste repozytorium `filmy` (bez README). Potem:

```powershell
git init
git add .
git commit -m "Aplikacja: lista filmow (Flask + PostgreSQL) + Dockerfile"
git branch -M main
git remote add origin https://github.com/TWOJ_LOGIN_GITHUB/filmy.git
git push -u origin main
```

## Krok 6. Włącz Kubernetes w Docker Desktop (przygotowanie do etapu 2)

Docker Desktop → **Settings** (koło zębate) → **Kubernetes** → zaznacz **Enable Kubernetes**. Jeśli pyta o typ klastra, wybierz **kubeadm** (jeden węzeł). Kliknij **Apply & restart** i poczekaj, aż ikona Kubernetes w dolnym pasku będzie zielona (kilka minut).

Sprawdzenie:

```powershell
kubectl config use-context docker-desktop
kubectl get nodes
```

Powinien być jeden węzeł `docker-desktop` w stanie `Ready`.

**Gotowe, gdy:** aplikacja działa lokalnie, obrazy `v1` i `v2` są na Docker Hub, kod jest na GitHubie, a `kubectl get nodes` pokazuje `Ready`.
