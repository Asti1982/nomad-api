# Azure Integration für Nomad - Kostenlos (Ohne Budget)

## Überblick

Nomad kann jetzt kostenlose Azure-Services entdecken und nutzen. Das ist perfekt für Agenten, die von Azure-Infrastruktur profitieren möchten, ohne Geld auszugeben.

## Kostenlose Azure-Services für Agenten

| Service | Limit | Best For | Automation |
|---------|-------|----------|------------|
| **Azure Functions** | 1M Anfragen/Monat + 400k GB-Sekunden | API-Endpoints, geplante Tasks | Exzellent |
| **Azure Static Web Apps** | 100 GB Bandbreite/Monat | Agent-Dashboards, Web-UIs | Exzellent |
| **Managed Identity** | Unbegrenzt | Sichere Agent-Authentifizierung | Exzellent |
| **Key Vault** | 10k Transaktionen/Monat | Secrets-Management | Gut |
| **Blob Storage** | 5 GB | Agent-Daten, Modelle | Gut |
| **Cosmos DB** | 1k RUs/Monat + 25 GB | NoSQL-Datenbank | Gut |
| **Log Analytics** | 5 GB/Tag Ingestion | Monitoring & Debugging | Gut |
| **Container Instances** | 4 vCPU-Stunden/Monat* | Docker-Container laufen lassen | Gut |

*Kostenlos mit Azure Free Account Credits

## Schnelle Schritte zum Start

### 1. Azure CLI Installation
```bash
# Windows (PowerShell)
choco install azure-cli
# oder von https://learn.microsoft.com/cli/azure/install-azure-cli

# Authentifizierung
az login
```

### 2. Kostenlose Azure-Optionen in Nomad erkunden
```bash
# Alle kostenlosen Azure-Services sehen
python main.py --cli scout azure

# Spezifisch nach Azure Functions fragen
python main.py --cli unlock azure --json
```

### 3. Ein Service aktivieren (z.B. Azure Functions)

```bash
# Details für Azure Functions bekommen
python main.py --cli scout compute
```

## Integration mit Nomad's Infrastructure-Scouting

Nomad erkennt automatisch:
- Kostenlose Tier-Limits
- Zuverlässigkeitsbewertungen
- Automatisierungspotenzial

### Beispiel in Code:

```python
from infra_scout import InfrastructureScout

scout = InfrastructureScout()

# Beste Azure-Option für Compute finden
options = scout.activation_request(category="azure")
print(options)
```

### Direkt Azure Scout verwenden:

```python
from azure_scout import scout_free_azure, AzureScout

# Übersicht aller kostenlosen Azure-Services
result = scout_free_azure()
print(result)

# Spezifisches Service aktivieren
scout = AzureScout()
request = scout.activation_request("azure-functions-free")
print(request)
```

## Praktische Anwendungsfälle für Agenten

### Use Case 1: API-Endpoint für Agent-Service
```bash
# Azure Functions bietet 1M kostenlose Requests/Monat
# Perfekt für Nomad's Service Desk
az functionapp create --resource-group nomad-rg \
  --consumption-plan-location eastus \
  --name nomad-api \
  --storage-account nomadstorage
```

### Use Case 2: Agent-Dashboard hosten
```bash
# Azure Static Web Apps: Kostenlos, auto-deploy via GitHub Actions
# Perfekt für Agent-UI, Status-Dashboard
```

### Use Case 3: Sichere Credential-Verwaltung
```bash
# Azure Key Vault (kostenlos, sichere Speicherung)
# Azure Managed Identity (kostenlos, keine Secrets nötig)
# Nomad kann Secrets sicher verwalten
```

### Use Case 4: Agent-Daten und Modelle speichern
```bash
# Azure Blob Storage: 5 GB kostenlos
# Perfekt für Agent-Outputs, heruntergeladene Modelle
```

## Empfohlener Startup-Pfad (Kostenlos)

1. **Managed Identity** (kostenlos, Identität für Agenten)
   ↓
2. **GitHub Models** (kostenlos, Inference)
   ↓
3. **Static Web Apps** (100 GB/Monat kostenlos)
   ↓
4. **Azure Functions** (1M Requests/Monat kostenlos)
   ↓
5. **Key Vault** (Secrets sicher speichern)

## Wichtige Hinweise

### ✅ Was funktioniert kostenlos
- Azure Functions: 1M Requests/Monat
- Static Web Apps: 100 GB Bandbreite/Monat
- Managed Identity: Unbegrenzt
- GitHub Models: Kostenlos (Microsoft-backed)
- Azure CLI: Kostenlos (nur für Verwaltung)

### ⚠️ Was überschreitet das kostenlose Limit
- **Zu viele Requests** → Kosten beginnen (~$0.20 pro 1M)
- **Zu viel Speicher** → Nach 5 GB kosten (~$0.018/GB)
- **Container-Stunden** → Nach 4 Stunden/Monat (~$0.0015/Sekunde)

### 🛡️ Sicherheit
- Managed Identity: Keine Secrets in Environment-Variablen nötig
- Key Vault: Verschlüsselte Credential-Speicherung
- Log Analytics: Vollständige Audit-Trails

## Fehlerbehandlung

### Azure CLI nicht installiert?
```bash
# Installation
choco install azure-cli  # Windows
brew install azure-cli   # macOS
apt-get install azure-cli # Linux
```

### Nicht authentifiziert?
```bash
az login
# Öffnet Browser für Microsoft-Login
```

### Kostenlos-Limits überschritten?
→ Nomad erkennt das und schlägt alternative freie Optionen vor
→ Oder manuell upgraden zu kostenpflichtigen Tiers wenn nötig

## Tests laufen lassen

```bash
# Azure Scout Integration testen
pytest test_azure_scout.py -v

# Oder direkt:
python test_azure_scout.py
```

## Weitere Ressourcen

- [Azure Free Account](https://azure.microsoft.com/free)
- [Azure Functions Free Tier](https://learn.microsoft.com/azure/azure-functions/functions-overview)
- [Azure Static Web Apps](https://learn.microsoft.com/azure/static-web-apps/overview)
- [Managed Identity](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/overview)

## Zusammenfassung

**Nomad kann jetzt kostenlos auf Azure-Infrastruktur zugreifen!**

- ✅ 9 kostenlose Azure-Services entdeckbar
- ✅ Automatische Tier-Limits und Kosten-Tracking
- ✅ Sichere Identität ohne Secrets
- ✅ Vollständig kostenlos ohne Ausgaben
- ✅ Integration mit Nomad's Self-Improvement-Zyklen

Der Ansatz: **Freie Open-Source-Compute-Lanes nutzen, um Nomad's eigene Fähigkeiten zu verbessern.**

---

Fragen? → `python main.py --cli scout azure --json`
