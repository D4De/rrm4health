#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEBAPP_REPO_DIR="$ROOT_DIR/webapp"
IOMT_DIR="$WEBAPP_REPO_DIR"
FRAMEWORK_DIR="$ROOT_DIR/framework"
RUN_DIR="$ROOT_DIR/.run_single_node"
LOG_DIR="$ROOT_DIR/LOG_single_node"

GLOBAL_PID_FILE="$RUN_DIR/rrm_global.pid"
LOCAL_PID_FILE="$RUN_DIR/rrm_local.pid"
WEBAPP_PID_FILE="$RUN_DIR/webapp.pid"

GLOBAL_LOG="$LOG_DIR/rrm_global.log"
LOCAL_LOG="$LOG_DIR/rrm_local.log"
WEBAPP_LOG="$LOG_DIR/webapp.log"

DOCKER_CMD=(docker)
COMPOSE_CMD=()

GLOBAL_IP="127.0.0.1"

DEFAULT_MQTT_TOPIC="aaac/campaign/#"
DEFAULT_MQTT_CLIENT_ID="bsn-webapp-sse-01"
DEFAULT_RRM_IP="127.0.0.1"
DEFAULT_RRM_PORT="41798"

LOCAL_MQTT_IP="localhost"
LOCAL_MQTT_PORT="1883"
LOCAL_MQTT_TOPIC="$DEFAULT_MQTT_TOPIC"
LOCAL_INFLUX_IP="localhost"
LOCAL_INFLUX_PORT="8086"
LOCAL_INFLUX_DATABASE="bsn_timeseries"

CRISTIANA_MQTT_IP="131.175.120.117"
CRISTIANA_MQTT_PORT="1883"
CRISTIANA_MQTT_TOPIC="$DEFAULT_MQTT_TOPIC"
CRISTIANA_INFLUX_IP="131.175.120.117"
CRISTIANA_INFLUX_PORT="8086"
CRISTIANA_INFLUX_DATABASE="iomdb"

usage() {
  cat <<'EOF'
Uso: ./StartSingleNode.sh [start|stop|status|logs] [opzioni]

Comandi:
  start    Avvia tutto (default): DB Docker + WebApp + RRM Global + RRM Local
  stop     Ferma tutti i processi avviati con questo script
  status   Mostra stato componenti
  logs     Mostra i file di log

Opzioni per start:
  --rebuild-webapp    Forza build Maven della WebApp anche se il jar esiste gia
  --update-webapp     Alias compatibile di --rebuild-webapp; usa i sorgenti locali
  --skip-system-install  Salta installazione automatica dipendenze di sistema (apt)
  --skip-tests        Usa Maven con -DskipTests durante clean package
  --compile-only      Esegue solo ./mvnw compile e termina senza avviare i processi
  --fix-webapp-encoding  Verifica e converte application.properties in UTF-8 se necessario
  --skip-db-config       Salta configurazione guidata MQTT/Influx
  --processes-only       Avvia solo WebApp + RRM Global + RRM Local, senza install/config/compose/build

Esempi:
  ./StartSingleNode.sh
  ./StartSingleNode.sh start --rebuild-webapp
  ./StartSingleNode.sh start --update-webapp
  ./StartSingleNode.sh start --skip-system-install
  ./StartSingleNode.sh start --skip-tests
  ./StartSingleNode.sh start --compile-only
  ./StartSingleNode.sh start --fix-webapp-encoding
  ./StartSingleNode.sh start --processes-only
  ./StartSingleNode.sh status
  ./StartSingleNode.sh stop
EOF
}

info() { echo "[INFO] $*"; }
warn() { echo "[WARN] $*"; }
err() { echo "[ERROR] $*" >&2; }

ensure_dir() {
  mkdir -p "$RUN_DIR" "$LOG_DIR"
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

python_venv_works() {
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  if python3 -m venv "$tmp_dir/venv" >/dev/null 2>&1; then
    rm -rf "$tmp_dir"
    return 0
  fi
  rm -rf "$tmp_dir"
  return 1
}

run_framework_install() {
  local install_script="$ROOT_DIR/install/Install.sh"

  if [[ ! -f "$install_script" ]]; then
    err "Script di installazione non trovato: $install_script"
    exit 1
  fi

  if [[ -d "$ROOT_DIR/venv" && ! -x "$ROOT_DIR/venv/bin/python" ]]; then
    warn "Virtualenv esistente ma incompleto: lo rimuovo e lo ricreo."
    rm -rf "$ROOT_DIR/venv"
  fi

  info "Eseguo install/Install.sh prima di avviare RRM..."
  info "La prima esecuzione puo richiedere tempo per creazione venv e dipendenze."
  (cd "$ROOT_DIR" && bash "$install_script")
}

install_system_dependencies_if_needed() {
  # Installazione automatica supportata su Linux Debian/Ubuntu (apt).
  if [[ "$(uname -s)" != "Linux" ]]; then
    warn "Installazione automatica dipendenze di sistema supportata solo su Linux."
    return
  fi

  if ! command_exists apt-get; then
    warn "apt-get non trovato: salto installazione automatica dipendenze di sistema."
    return
  fi

  local -a apt_prefix=()
  if [[ "$(id -u)" -ne 0 ]]; then
    if ! command_exists sudo; then
      err "sudo non trovato. Installa sudo o esegui lo script come root."
      exit 1
    fi
    apt_prefix=(sudo)
  fi

  local -a packages=()
  local needs_java="0"

  if ! command_exists python3; then
    packages+=(python3 python3-venv)
  elif ! python_venv_works; then
    local python_version
    python_version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
    if [[ -n "$python_version" ]]; then
      packages+=("python${python_version}-venv")
    fi
    packages+=(python3-venv)
  fi

  if ! command_exists git; then
    packages+=(git)
  fi

  if ! command_exists docker; then
    packages+=(docker.io)
  fi

  if ! (command_exists docker && docker compose version >/dev/null 2>&1) && ! command_exists docker-compose; then
    packages+=(docker-compose-v2)
  fi

  if ! command_exists java; then
    needs_java="1"
  fi

  if [[ ${#packages[@]} -gt 0 || "$needs_java" == "1" ]]; then
    info "Installazione dipendenze di sistema mancanti..."
    "${apt_prefix[@]}" apt-get update
  else
    info "Dipendenze di sistema gia presenti, salto installazione apt."
  fi

  if [[ ${#packages[@]} -gt 0 ]]; then
    "${apt_prefix[@]}" apt-get install -y "${packages[@]}"
  fi

  if [[ "$needs_java" == "1" ]]; then
    info "Installazione Java (tentativo openjdk-25-jre-headless + openjdk-25-jdk-headless)..."
    if ! "${apt_prefix[@]}" apt-get install -y openjdk-25-jre-headless openjdk-25-jdk-headless; then
      warn "openjdk-25 non disponibile, uso fallback openjdk-21/default-jdk."
      if ! "${apt_prefix[@]}" apt-get install -y openjdk-21-jdk-headless; then
        "${apt_prefix[@]}" apt-get install -y default-jdk-headless
      fi
    fi
  fi

  if command_exists docker; then
    if command_exists systemctl; then
      "${apt_prefix[@]}" systemctl enable docker >/dev/null 2>&1 || warn "Impossibile abilitare docker al boot."
      "${apt_prefix[@]}" systemctl start docker >/dev/null 2>&1 || warn "Impossibile avviare servizio docker automaticamente."
      "${apt_prefix[@]}" systemctl status docker >/dev/null 2>&1 || warn "Servizio docker non risulta attivo."
    fi

    if getent group docker >/dev/null 2>&1; then
      if ! id -nG "$USER" | grep -qw docker; then
        if "${apt_prefix[@]}" usermod -aG docker "$USER"; then
          warn "Utente aggiunto al gruppo docker: serve logout/login per usare docker senza sudo."
        fi
      fi
    fi
  fi
}

check_docker_ready() {
  if command_exists systemctl; then
    if ! systemctl status docker >/dev/null 2>&1; then
      warn "docker service non attivo o non interrogabile senza privilegi."
    fi
  fi

  if docker ps >/dev/null 2>&1; then
    DOCKER_CMD=(docker)
    return
  fi

  if [[ "$(id -u)" -eq 0 ]]; then
    err "docker ps fallito anche come root. Verifica che Docker sia installato e avviato."
    exit 1
  fi

  if ! command_exists sudo; then
    err "docker ps fallito e sudo non e disponibile."
    err "Dopo usermod -aG docker $USER serve logout/login, oppure esegui lo script come root."
    exit 1
  fi

  warn "Docker non e ancora accessibile senza sudo in questa sessione."
  warn "Uso sudo docker per completare questa esecuzione; dopo logout/login non sara piu necessario."

  if sudo docker ps >/dev/null 2>&1; then
    DOCKER_CMD=(sudo docker)
    return
  fi

  err "sudo docker ps fallito. Verifica che Docker sia installato, avviato e che l'utente possa usare sudo."
  exit 1
}

fix_webapp_encoding_if_requested() {
  local fix_requested="$1"
  local prop_file="$IOMT_DIR/src/main/resources/application.properties"

  if [[ "$fix_requested" != "1" ]]; then
    return
  fi

  if [[ ! -f "$prop_file" ]]; then
    warn "File non trovato, salto check encoding: $prop_file"
    return
  fi

  if ! command_exists file; then
    warn "Comando 'file' non disponibile, salto check encoding application.properties."
    return
  fi

  if ! command_exists iconv; then
    warn "Comando 'iconv' non disponibile, salto conversione encoding."
    return
  fi

  local encoding
  encoding="$(file -bi "$prop_file" | tr '[:upper:]' '[:lower:]')"
  info "Encoding attuale application.properties: $encoding"

  if echo "$encoding" | grep -q "charset=utf-8"; then
    info "application.properties e gia UTF-8."
    return
  fi

  local tmp_file
  tmp_file="$(mktemp "$IOMT_DIR/application.properties.XXXXXX")"

  if iconv -f ISO-8859-1 -t UTF-8 "$prop_file" -o "$tmp_file"; then
    mv "$tmp_file" "$prop_file"
    info "application.properties convertito in UTF-8."
  else
    rm -f "$tmp_file"
    err "Conversione encoding fallita per $prop_file"
    exit 1
  fi
}


prompt_required() {
  local label="$1"
  local default_value="${2:-}"
  local value=""

  while [[ -z "$value" ]]; do
    if [[ -n "$default_value" ]]; then
      read -r -p "$label [$default_value]: " value
      value="${value:-$default_value}"
    else
      read -r -p "$label: " value
    fi
    value="$(trim "$value")"
  done

  echo "$value"
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  echo "$value"
}

write_properties_value() {
  local file="$1"
  local key="$2"
  local value="$3"

  mkdir -p "$(dirname "$file")"
  touch "$file"

  local escaped
  escaped="$(printf '%s' "$value" | sed 's/[&\\]/\\&/g')"

  if grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${escaped}|" "$file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$file"
  fi
}

write_mqtt_runtime_config() {
  local mqtt_ip="$1"
  local mqtt_port="$2"
  local mqtt_topic="$3"
  local mqtt_file="$IOMT_DIR/data/mqtt-runtime.properties"

  mkdir -p "$(dirname "$mqtt_file")"
  cat > "$mqtt_file" <<EOF_MQTT
# MQTT runtime configuration
app.mqtt.enabled=true
app.mqtt.broker=tcp://${mqtt_ip}:${mqtt_port}
app.mqtt.topic=${mqtt_topic}
app.mqtt.client-id=${DEFAULT_MQTT_CLIENT_ID}
app.mqtt.username=
app.mqtt.password=
app.mqtt.qos=0
EOF_MQTT
}

sql_escape() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\'/\'\'}"
  echo "$value"
}

generate_database_config_sql() {
  local influx_ip="$1"
  local influx_port="$2"
  local influx_database="$3"
  local setup_dir="$IOMT_DIR/setupdata"
  local sql_file="$setup_dir/zz_database_config.sql"
  local host="${influx_ip}:${influx_port}"
  local name="Influx ${influx_ip}"

  mkdir -p "$setup_dir"
  cat > "$sql_file" <<EOF_SQL
USE \`bsn_db\`;

DELETE FROM \`database_config\`;
ALTER TABLE \`database_config\` AUTO_INCREMENT = 1;
INSERT INTO \`database_config\` (\`id_database\`, \`db_name\`, \`host\`, \`nome\`) VALUES
(1, '$(sql_escape "$influx_database")', '$(sql_escape "$host")', '$(sql_escape "$name")');

DELETE FROM \`setting\` WHERE \`id\` IN (1, 2) OR \`key_name\` IN ('rrm.ip', 'rrm.port');
ALTER TABLE \`setting\` AUTO_INCREMENT = 1;
INSERT INTO \`setting\` (\`id\`, \`key_name\`, \`value\`) VALUES
(1, 'rrm.ip', '$(sql_escape "$DEFAULT_RRM_IP")'),
(2, 'rrm.port', '$(sql_escape "$DEFAULT_RRM_PORT")');
EOF_SQL
}

configure_mqtt_and_influx() {
  local mqtt_ip=""
  local mqtt_port=""
  local mqtt_topic=""
  local influx_ip=""
  local influx_port=""
  local influx_database=""

  echo
  info "Configurazione DB, MQTT e InfluxDB"
  echo "1) Locale (Mosquitto + InfluxDB Docker locali)"
  echo "2) DB Cristiana"
  echo "3) Manuale"

  local choice=""
  while [[ ! "$choice" =~ ^[123]$ ]]; do
    read -r -p "Seleziona configurazione [1-3]: " choice
  done

  case "$choice" in
    1)
      mqtt_ip="$LOCAL_MQTT_IP"
      mqtt_port="$LOCAL_MQTT_PORT"
      mqtt_topic="$LOCAL_MQTT_TOPIC"
      influx_ip="$LOCAL_INFLUX_IP"
      influx_port="$LOCAL_INFLUX_PORT"
      influx_database="$LOCAL_INFLUX_DATABASE"
      ;;
    2)
      mqtt_ip="$CRISTIANA_MQTT_IP"
      mqtt_port="$CRISTIANA_MQTT_PORT"
      mqtt_topic="$CRISTIANA_MQTT_TOPIC"
      influx_ip="$CRISTIANA_INFLUX_IP"
      influx_port="$CRISTIANA_INFLUX_PORT"
      influx_database="$CRISTIANA_INFLUX_DATABASE"
      ;;
    3)
      echo
      info "Configurazione MQTT manuale"
      mqtt_ip="$(prompt_required "IP/host broker MQTT" "localhost")"
      mqtt_port="$(prompt_required "Porta broker MQTT" "1883")"
      mqtt_topic="$(prompt_required "Filtro topic MQTT" "$DEFAULT_MQTT_TOPIC")"

      echo
      info "Configurazione InfluxDB manuale"
      influx_ip="$(prompt_required "IP/host InfluxDB" "localhost")"
      influx_port="$(prompt_required "Porta InfluxDB" "8086")"
      influx_database="$(prompt_required "Nome database InfluxDB" "bsn_timeseries")"
      ;;
  esac

  write_mqtt_runtime_config "$mqtt_ip" "$mqtt_port" "$mqtt_topic"
  generate_database_config_sql "$influx_ip" "$influx_port" "$influx_database"

  info "Configurazione salvata:"
  echo "- MQTT: tcp://${mqtt_ip}:${mqtt_port} topic=${mqtt_topic}"
  echo "- InfluxDB: http://${influx_ip}:${influx_port} database=${influx_database}"
  echo
}

ensure_webapp_source() {
  if [[ -d "$WEBAPP_REPO_DIR" ]]; then
    return
  fi

  err "WebApp inclusa nel repository non trovata: $WEBAPP_REPO_DIR"
  err "Ripristina la cartella webapp/ dal repository rrm4health."
  exit 1
}

resolve_iomt_dir() {
  if [[ -f "$WEBAPP_REPO_DIR/pom.xml" && -f "$WEBAPP_REPO_DIR/docker-compose.yml" ]]; then
    IOMT_DIR="$WEBAPP_REPO_DIR"
    return
  fi

  err "WebApp incompleta. File richiesti:"
  err "- $WEBAPP_REPO_DIR/pom.xml"
  err "- $WEBAPP_REPO_DIR/docker-compose.yml"
  exit 1
}

get_python_bin() {
  if [[ -x "$ROOT_DIR/venv/bin/python" ]]; then
    echo "$ROOT_DIR/venv/bin/python"
    return
  fi

  if command_exists python3; then
    echo "python3"
    return
  fi

  err "python3 non trovato. Installa Python 3.10+ e riprova."
  exit 1
}

configure_compose_cmd() {
  if command_exists docker && "${DOCKER_CMD[@]}" compose version >/dev/null 2>&1; then
    COMPOSE_CMD=("${DOCKER_CMD[@]}" compose)
    return
  fi

  if command_exists docker-compose; then
    if docker-compose version >/dev/null 2>&1; then
      COMPOSE_CMD=(docker-compose)
      return
    fi

    if [[ "${DOCKER_CMD[0]}" == "sudo" ]] && sudo docker-compose version >/dev/null 2>&1; then
      COMPOSE_CMD=(sudo docker-compose)
      return
    fi
  fi

  err "Docker Compose non trovato. Installa Docker + Compose e riprova."
  exit 1
}

wait_for_mariadb() {
  local attempts=90

  for ((i = 1; i <= attempts; i++)); do
    if "${DOCKER_CMD[@]}" exec bsn_mariadb mariadb-admin ping -uroot -prootpwd --silent >/dev/null 2>&1; then
      return 0
    fi

    if (( i % 10 == 0 )); then
      info "Attendo MariaDB... tentativo ${i}/${attempts}"
    fi

    sleep 2
  done

  return 1
}

ensure_setupdata_files() {
  local setup_dir="$IOMT_DIR/setupdata"
  local -a required_files=("initdb.sql" "initdb.insert.sql" "zz_database_config.sql")
  local missing="0"

  for file_name in "${required_files[@]}"; do
    if [[ ! -f "$setup_dir/$file_name" ]]; then
      err "File SQL mancante: $setup_dir/$file_name"
      missing="1"
    fi
  done

  if [[ "$missing" == "1" ]]; then
    err "La cartella setupdata non è completa: aggiorna la WebApp o copia i file SQL prima di avviare."
    exit 1
  fi
}

apply_setup_sql_to_running_db() {
  local setup_dir="$IOMT_DIR/setupdata"
  local -a sql_files=(
    "$setup_dir/initdb.sql"
    "$setup_dir/initdb.insert.sql"
    "$setup_dir/zz_database_config.sql"
  )

  if ! wait_for_mariadb; then
    err "MariaDB non pronto: impossibile importare schema e dati iniziali."
    exit 1
  fi

  for sql_file in "${sql_files[@]}"; do
    info "Importo SQL: $sql_file"
    "${DOCKER_CMD[@]}" exec -i bsn_mariadb mariadb -uroot -prootpwd bsn_db < "$sql_file"
  done

  info "Schema e dati iniziali MariaDB applicati."
}

is_pid_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

read_pid() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    cat "$pid_file"
  fi
}

is_component_running() {
  local pid_file="$1"
  local pid
  pid="$(read_pid "$pid_file" || true)"
  [[ -n "$pid" ]] && is_pid_running "$pid"
}

start_component() {
  local name="$1"
  local pid_file="$2"
  local log_file="$3"
  local cmd="$4"

  if is_component_running "$pid_file"; then
    local pid
    pid="$(read_pid "$pid_file")"
    warn "$name e gia in esecuzione (PID $pid)."
    return
  fi

  : > "$log_file"
  nohup bash -lc "$cmd" >"$log_file" 2>&1 &
  local pid=$!
  echo "$pid" > "$pid_file"
  info "$name avviato (PID $pid)."
}

stop_component() {
  local name="$1"
  local pid_file="$2"

  if [[ ! -f "$pid_file" ]]; then
    info "$name non risulta avviato da questo script."
    return
  fi

  local pid
  pid="$(cat "$pid_file")"

  if is_pid_running "$pid"; then
    kill "$pid" >/dev/null 2>&1 || true
    sleep 1
    if is_pid_running "$pid"; then
      warn "$name non si e fermato subito, invio SIGKILL."
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    info "$name fermato."
  else
    info "$name non era piu in esecuzione."
  fi

  rm -f "$pid_file"
}

print_status_line() {
  local name="$1"
  local pid_file="$2"

  if is_component_running "$pid_file"; then
    local pid
    pid="$(read_pid "$pid_file")"
    echo "- $name: RUNNING (PID $pid)"
  else
    echo "- $name: STOPPED"
  fi
}

build_webapp_if_needed() {
  local rebuild="$1"
  local skip_tests="$2"
  local compile_only="$3"

  local jar
  jar="$(find "$IOMT_DIR/target" -maxdepth 1 -type f -name '*.jar' ! -name '*.original' | head -n 1 || true)"

  if [[ "$compile_only" == "1" ]]; then
    info "Compilazione solo classi WebApp con Maven Wrapper (./mvnw compile)..."
    (cd "$IOMT_DIR" && ./mvnw compile)
    return
  fi

  if [[ "$rebuild" == "1" || -z "$jar" ]]; then
    if [[ "$skip_tests" == "1" ]]; then
      info "Compilazione WebApp con Maven Wrapper (./mvnw clean package -DskipTests)..."
      (cd "$IOMT_DIR" && ./mvnw clean package -DskipTests)
    else
      info "Compilazione WebApp con Maven Wrapper (./mvnw clean package)..."
      (cd "$IOMT_DIR" && ./mvnw clean package)
    fi
  else
    info "Jar WebApp gia presente, salto la compilazione (usa --rebuild-webapp per forzarla)."
  fi
}

get_webapp_jar() {
  local jar
  jar="$(find "$IOMT_DIR/target" -maxdepth 1 -type f -name '*.jar' ! -name '*.original' | head -n 1 || true)"

  if [[ -z "$jar" ]]; then
    err "Jar WebApp non trovato in webapp/target."
    exit 1
  fi

  echo "$jar"
}

start_all() {
  local rebuild_webapp="0"
  local skip_system_install="0"
  local skip_tests="0"
  local compile_only="0"
  local fix_webapp_encoding="0"
  local skip_db_config="0"
  local processes_only="0"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --rebuild-webapp)
        rebuild_webapp="1"
        ;;
      --update-webapp)
        warn "--update-webapp usa i sorgenti locali come --rebuild-webapp; aggiorna il repository separatamente."
        rebuild_webapp="1"
        ;;
      --skip-system-install)
        skip_system_install="1"
        ;;
      --skip-tests)
        skip_tests="1"
        ;;
      --compile-only)
        compile_only="1"
        ;;
      --fix-webapp-encoding)
        fix_webapp_encoding="1"
        ;;
      --skip-db-config)
        skip_db_config="1"
        ;;
      --processes-only)
        processes_only="1"
        ;;
      *)
        err "Opzione non riconosciuta: $1"
        usage
        exit 1
        ;;
    esac
    shift
  done

  if [[ "$compile_only" == "1" && "$processes_only" == "1" ]]; then
    err "Opzioni incompatibili: --compile-only e --processes-only."
    exit 1
  fi

  ensure_dir

  if [[ "$processes_only" == "1" ]]; then
    warn "Modalita processes-only: salto installazione, configurazione, Docker Compose e build."
    if [[ ! -d "$WEBAPP_REPO_DIR" ]]; then
      err "WebApp non trovata: $WEBAPP_REPO_DIR"
      err "Esegui prima un avvio completo senza --processes-only."
      exit 1
    fi
    resolve_iomt_dir
  else
    if [[ "$skip_system_install" == "1" ]]; then
      warn "Installazione automatica dipendenze di sistema disabilitata (--skip-system-install)."
    else
      install_system_dependencies_if_needed
    fi

    ensure_webapp_source
    resolve_iomt_dir
    fix_webapp_encoding_if_requested "$fix_webapp_encoding"
  fi

  if [[ ! -f "$IOMT_DIR/docker-compose.yml" ]]; then
    err "File mancante: webapp/docker-compose.yml"
    exit 1
  fi

  if [[ ! -f "$IOMT_DIR/pom.xml" ]]; then
    err "File mancante: webapp/pom.xml"
    exit 1
  fi

  if ! command_exists java; then
    err "java non trovato. Installa Java 21+ e riprova."
    exit 1
  fi

  if [[ "$processes_only" != "1" && ! -x "$IOMT_DIR/mvnw" ]]; then
    err "Maven Wrapper non eseguibile: webapp/mvnw"
    err "Esegui: chmod +x webapp/mvnw"
    exit 1
  fi

  if [[ "$processes_only" != "1" ]]; then
    if [[ "$skip_db_config" == "1" ]]; then
      warn "Configurazione guidata MQTT/Influx saltata (--skip-db-config)."
    else
      configure_mqtt_and_influx
    fi
    ensure_setupdata_files

    check_docker_ready
    configure_compose_cmd

    run_framework_install

    info "Avvio database Docker (MariaDB + InfluxDB)..."
    (cd "$IOMT_DIR" && "${COMPOSE_CMD[@]}" up -d)
    apply_setup_sql_to_running_db

    build_webapp_if_needed "$rebuild_webapp" "$skip_tests" "$compile_only"
  fi

  local python_bin
  python_bin="$(get_python_bin)"

  if [[ "$compile_only" == "1" ]]; then
    info "Compilazione WebApp completata (modalita compile-only). Nessun processo avviato."
    return
  fi

  local jar_path
  jar_path="$(get_webapp_jar)"

  start_component "WebApp" "$WEBAPP_PID_FILE" "$WEBAPP_LOG" "cd '$IOMT_DIR' && java -jar '$jar_path'"
  start_component "RRM Global" "$GLOBAL_PID_FILE" "$GLOBAL_LOG" "cd '$FRAMEWORK_DIR' && '$python_bin' LaunchRrmGlobal.py --log_level INFO"

  # Lasciamo al global il tempo di aprire la porta prima di avviare il local.
  sleep 2
  start_component "RRM Local" "$LOCAL_PID_FILE" "$LOCAL_LOG" "cd '$FRAMEWORK_DIR' && '$python_bin' LaunchRrmLocal.py --global_ip '$GLOBAL_IP' --log_level INFO"

  echo
  info "Sistema avviato."
  echo "- WebApp: http://localhost:8080"
  echo "- Log WebApp: $WEBAPP_LOG"
  echo "- Log RRM Global: $GLOBAL_LOG"
  echo "- Log RRM Local: $LOCAL_LOG"
  echo
  info "Usa './StartSingleNode.sh status' per verificare lo stato e './StartSingleNode.sh stop' per fermare tutto."
}

stop_all() {
  stop_component "RRM Local" "$LOCAL_PID_FILE"
  stop_component "RRM Global" "$GLOBAL_PID_FILE"
  stop_component "WebApp" "$WEBAPP_PID_FILE"
  info "Arresto completato."
}

status_all() {
  echo "Stato componenti"
  print_status_line "WebApp" "$WEBAPP_PID_FILE"
  print_status_line "RRM Global" "$GLOBAL_PID_FILE"
  print_status_line "RRM Local" "$LOCAL_PID_FILE"
}

show_logs() {
  echo "Log principali"
  echo "- WebApp: $WEBAPP_LOG"
  echo "- RRM Global: $GLOBAL_LOG"
  echo "- RRM Local: $LOCAL_LOG"
}

main() {
  local cmd="${1:-start}"
  if [[ $# -gt 0 ]]; then
    shift
  fi

  case "$cmd" in
    start)
      start_all "$@"
      ;;
    stop)
      stop_all
      ;;
    status)
      status_all
      ;;
    logs)
      show_logs
      ;;
    -h|--help|help)
      usage
      ;;
    *)
      err "Comando non riconosciuto: $cmd"
      usage
      exit 1
      ;;
  esac
}

main "$@"
