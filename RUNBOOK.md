# Runbook: Benchmark auf einem fremden Rechner ausführen

Dieses Projekt erwartet eine funktionierende Ollama-API.

## 1) Voraussetzungen

- Docker
- Docker Compose
- Git (optional, aber empfohlen)
- Internetzugang zum Download der Images

## 2) Projekt holen

```bash
git clone <repo-url>
cd clinical-llm-benchmark
```

## 3) Starten der Modell-API

Das Projekt enthält einen Ollama-Service in `docker-compose.yml`.

```bash
docker-compose up -d ollama
```

Damit startet Ollama im selben Docker-Netzwerk wie der Benchmark-Container.

## 4) Benchmark ausführen

Der Benchmark liest die Docker-Konfiguration aus `config_with_docker.yaml` und greift per Compose-Netzwerk auf `http://ollama:11434` zu.

```bash
docker-compose run --rm benchmark
```

Wenn du den Benchmark mit einer benutzerdefinierten Datei oder einem eigenen Output starten willst:

```bash
docker-compose run --rm benchmark run_benchmark.py --config config.yaml --output results/my-run.jsonl
```

## 5) Wichtig: Was nicht genutzt werden darf

Nicht als Modell-Endpoint verwenden:
- Open Web UI
- ein Browser-Frontend
- irgendein Webserver, der nur HTML liefert

Der Benchmark-Adapter erwartet eine echte Ollama-API, also eine URL wie:
- `http://ollama:11434`
- `http://127.0.0.1:11434`
- `http://host.docker.internal:11434` (falls der Benchmark auf dem Host läuft, nicht im Compose-Netzwerk)

## 6) Konfiguration verstehen

Die Docker-spezifische Datei ist:
- `config_with_docker.yaml`

Dort muss der Modellserver auf den Docker-Service zeigen:

```yaml
base_url: http://ollama:11434
```

Wenn ein anderer Rechner oder Host verwendet wird, muss der Endpoint entsprechend angepasst werden, aber immer auf eine echte Ollama-API, nicht auf ein Frontend.

## 7) Output finden

Die Rohdaten werden im Ordner `results/` gespeichert.

```bash
ls -l results
```

## 8) Troubleshooting

Wenn der Benchmark nach dem Start `HTTP 405` oder `ConnectionError: inference stream failed` meldet, dann ist meist einer dieser Fälle der Grund:

- falscher Endpoint in der Config
- kein echter Ollama-Server erreichbar
- Open Web UI statt Ollama verwendet
- falscher Port oder nicht erreichbares Docker-Netzwerk
- das gewählte Modell passt nicht in die verfügbare RAM/Shared-Memory-Limitierung

Prüfen:

```bash
docker-compose ps
curl -i http://127.0.0.1:11434/api/tags
docker-compose exec ollama ollama list
docker-compose exec ollama ollama run qwen3:4b "Hallo"
```

Wenn `curl` auf `http://127.0.0.1:11434/api/tags` keinen gültigen JSON-Response liefert, ist Ollama nicht richtig erreichbar. Wenn `ollama run ...` mit `insufficient memory` oder `unable to allocate CPU_REPACK buffer` fehlschlägt, ist das Modell zu groß für die aktuelle VM/Container-RAM. In Colima ist ein größerer VM-Start häufig nötig, z. B.:

```bash
colima stop
colima start --cpu 4 --memory 12 --disk 80
```

Dann das Modell erneut ziehen/ausführen und den Benchmark neu starten.

## 9) Empfehlung

Für einen fremden Rechner oder eine fremde Umgebung ist die sauberste Variante:

- Das Projekt mit Docker/Compose ausführen
- Ollama als eigenständigen Service starten
- Nur `http://ollama:11434` als Modell-Backend benutzen
- Andere Frontends nicht als Modell-Endpoint konfigurieren
