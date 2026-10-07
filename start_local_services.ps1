param(
    [switch]$Install,
    [switch]$Start
)
$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

# ---------- INFLUXDB ----------
$INFLUX_VERSION = "2.9.1"
$INFLUX_DIR = "$ROOT\.local\influxdb"
$INFLUX_BIN = "$INFLUX_DIR\influxd.exe"
$INFLUX_ENGINE = "$INFLUX_DIR\engine"

function Install-InfluxDB {
    Write-Host "[1/2] Installation InfluxDB $INFLUX_VERSION ..."
    $url = "https://dl.influxdata.com/influxdb/releases/influxdb2-$INFLUX_VERSION-windows_amd64.zip"
    $zip = "$env:TEMP\influxdb.zip"
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    New-Item -ItemType Directory -Path $INFLUX_DIR -Force | Out-Null
    Expand-Archive -Path $zip -DestinationPath $INFLUX_DIR -Force
    Remove-Item -Path $zip -Force -ErrorAction SilentlyContinue
    Write-Host "InfluxDB installe dans $INFLUX_DIR"
}

function Start-InfluxDB {
    if (-not (Test-Path $INFLUX_BIN)) {
        Write-Host "InfluxDB non installe. Lance avec -Install d'abord." -ForegroundColor Red
        return
    }
    $proc = Get-Process -Name influxd -ErrorAction SilentlyContinue
    if ($proc) { Write-Host "InfluxDB deja lance (PID $($proc.Id))" -ForegroundColor Yellow; return }

    Write-Host "Demarrage InfluxDB sur port 8086 ..."
    $log = "$ROOT\.local\influxdb.log"
    $args = @(
        "--engine-path=`"$INFLUX_ENGINE`"",
        "--bolt-path=`"$INFLUX_DIR\influxd.bolt`"",
        "--http-bind-address=:8086",
        "--reporting-disabled"
    )
    Start-Process -NoNewWindow -FilePath $INFLUX_BIN -ArgumentList $args -RedirectStandardOutput $log -RedirectStandardError $log
    Start-Sleep -Seconds 3

    # Initialisation via API (premier lancement seulement)
    try {
        $body = @{
            username = "admin"
            password = "admin123"
            org = "orhan"
            bucket = "sensors"
            token = "admin123admin123admin123admin123ad=="
        } | ConvertTo-Json
        $r = Invoke-WebRequest -Uri "http://localhost:8086/api/v2/setup" -Method Post -Body $body -ContentType "application/json" -UseBasicParsing -TimeoutSec 5
        Write-Host "InfluxDB initialise (org=orhan, bucket=sensors)" -ForegroundColor Green
    } catch {
        Write-Host "InfluxDB deja initialise ou erreur: $($_.Exception.Message)" -ForegroundColor Yellow
    }
    Write-Host "InfluxDB: http://localhost:8086" -ForegroundColor Green
}

# ---------- KAFKA ----------
$KAFKA_VERSION = "3.5.0"
$KAFKA_DIR = "$ROOT\.local\kafka"
$KAFKA_BIN = "$KAFKA_DIR\bin\windows"

function Install-Kafka {
    Write-Host "[2/2] Installation Kafka $KAFKA_VERSION ..."
    $url = "https://archive.apache.org/dist/kafka/$KAFKA_VERSION/kafka_2.13-$KAFKA_VERSION.tgz"
    $tgz = "$env:TEMP\kafka.tgz"
    Invoke-WebRequest -Uri $url -OutFile $tgz -UseBasicParsing
    # Extraction avec tar (Windows 10+)
    New-Item -ItemType Directory -Path "$env:TEMP\kafka_extract" -Force | Out-Null
    tar -xzf $tgz -C "$env:TEMP\kafka_extract"
    New-Item -ItemType Directory -Path $KAFKA_DIR -Force | Out-Null
    Copy-Item "$env:TEMP\kafka_extract\*\*" -Destination $KAFKA_DIR -Recurse -Force
    Remove-Item -Path $tgz, "$env:TEMP\kafka_extract" -Recurse -Force
    Write-Host "Kafka installe dans $KAFKA_DIR"
}

function Start-Kafka {
    if (-not (Test-Path "$KAFKA_BIN\zookeeper-server-start.bat")) {
        Write-Host "Kafka non installe. Lance avec -Install d'abord." -ForegroundColor Red
        return
    }
    $log = "$ROOT\.local"

    # Zookeeper
    $zk = Get-Process -Name zookeeper -ErrorAction SilentlyContinue
    if (-not $zk) {
        Write-Host "Demarrage Zookeeper sur port 2181 ..."
        Start-Process -NoNewWindow -FilePath "$KAFKA_BIN\zookeeper-server-start.bat" `
            -ArgumentList "$KAFKA_DIR\config\zookeeper.properties" `
            -RedirectStandardOutput "$log\zookeeper.log" -RedirectStandardError "$log\zookeeper.err"
        Start-Sleep -Seconds 4
        Write-Host "Zookeeper: http://localhost:2181" -ForegroundColor Green
    } else {
        Write-Host "Zookeeper deja lance" -ForegroundColor Yellow
    }

    # Kafka broker
    $kb = Get-Process -Name kafka -ErrorAction SilentlyContinue
    if (-not $kb) {
        Write-Host "Demarrage Kafka sur port 9092 ..."
        # Config personnalisee avec advertised listeners
        $props = @"
num.partitions=3
log.dirs=$KAFKA_DIR\data
"@
        Set-Content -Path "$KAFKA_DIR\config\server.properties" -Value (Get-Content "$KAFKA_DIR\config\server.properties" | `
            ForEach-Object { $_ -replace "log.dirs=.*", "log.dirs=$KAFKA_DIR\data" } | `
            ForEach-Object { $_ -replace "#listeners=PLAINTEXT://:9092", "listeners=PLAINTEXT://0.0.0.0:9092" } | `
            ForEach-Object { $_ -replace "#advertised.listeners=PLAINTEXT://your.host.name:9092", "advertised.listeners=PLAINTEXT://localhost:9092" })
        Start-Process -NoNewWindow -FilePath "$KAFKA_BIN\kafka-server-start.bat" `
            -ArgumentList "$KAFKA_DIR\config\server.properties" `
            -RedirectStandardOutput "$log\kafka.log" -RedirectStandardError "$log\kafka.err"
        Start-Sleep -Seconds 5
        Write-Host "Kafka: http://localhost:9092" -ForegroundColor Green
    } else {
        Write-Host "Kafka deja lance" -ForegroundColor Yellow
    }

    # Creer le topic
    & "$KAFKA_BIN\kafka-topics.bat" --create --topic sensors-raw --partitions 3 --replication-factor 1 --bootstrap-server localhost:9092 2>$null
    Write-Host "Topic 'sensors-raw' cree" -ForegroundColor Green
}

# ---------- MAIN ----------
try {
    if ($Install) {
        Install-InfluxDB
        Install-Kafka
        Write-Host "`nInstallation terminee. Lance avec -Start" -ForegroundColor Green
    }
    elseif ($Start) {
        Start-InfluxDB
        Start-Kafka
        Write-Host "`nServices demarres !" -ForegroundColor Green
        Write-Host "  InfluxDB: http://localhost:8086" -ForegroundColor Cyan
        Write-Host "  Kafka:    http://localhost:9092" -ForegroundColor Cyan
        Write-Host "`nPour arreter: Get-Process influxd, java | Stop-Process" -ForegroundColor Gray
    }
    else {
        Write-Host "Usage:" -ForegroundColor Yellow
        Write-Host "  .\start_local_services.ps1 -Install   # Telecharge et installe InfluxDB + Kafka"
        Write-Host "  .\start_local_services.ps1 -Start     # Lance les services"
        Write-Host "`nOU lance Docker Desktop et reessaye: docker-compose up -d" -ForegroundColor Cyan
    }
}
catch {
    Write-Host "ERREUR: $_" -ForegroundColor Red
}
