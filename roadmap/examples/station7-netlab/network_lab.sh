#!/usr/bin/env bash
# Учебный стенд 7Б. Запускать up/down ТОЛЬКО внутри одноразовой Linux VM.
# Namespace — не граница безопасности для недоверенного root-процесса.
# Скрипт не настраивает сеть хоста, не запускает службы и не выходит в интернет.
set -Eeuo pipefail
export LC_ALL=C
umask 077

readonly STATE_DIR=/run/cpp-course-netlab7
readonly NETNS_DIR=/run/netns
readonly MANIFEST="$STATE_DIR/manifest"
readonly -a NAMES=(nl7-client nl7-peer nl7-router nl7-server)
declare -A OWNED=()
TOKEN=''
READY=0
STATE_CREATED=0
CONFIRMED=0

usage() {
    printf '%s\n' \
        'Учебная сеть 7Б — только внутри одноразовой Linux VM.' \
        'Использование: bash network_lab.sh [help|check|status|up|down] [--inside-disposable-vm]' \
        '' \
        'help    По умолчанию: только эта справка.' \
        'check   Read-only: зависимости, UID, флаг подтверждения, занятые имена.' \
        'status  Read-only: состояние manifest; с UID 0 также адреса и маршруты.' \
        'up      Создать стенд; нужны UID 0 и --inside-disposable-vm.' \
        'down    Удалить только подтверждённые ресурсы стенда; те же требования.' \
        '' \
        'Флаг — ваше подтверждение, НЕ автоматическое доказательство запуска в VM.' \
        'Не запускайте up/down на рабочем компьютере, сервере или в shared/container-среде.' \
        'Снимок VM и отсутствие ценных данных проверяются вами до запуска.' \
        '' \
        'nl7-client eth0 --- lan-client [br-lan nl7-router] wan0 --- eth0 nl7-server' \
        'nl7-peer   eth0 --- lan-peer  [тот же br-lan]' \
        'LAN: 192.0.2.0/24; 2001:db8:7:1::/64. WAN: 198.51.100.0/24; 2001:db8:7:2::/64.' \
        'router: .1/::1; client: .10/::10; peer: .11/::11; server: .10/::10 в WAN.' \
        'Default route есть только внутри client/peer/server и ведёт к router.' \
        'Нет NAT, DHCP, DNS, RA/SLAAC-служб, внешнего подключения или host bridge.' \
        'IPv6 настраивается статически; link-local и Neighbor Discovery остаются включены.' \
        'Нужен python3 (только stdlib): down разбирает JSON iproute2 и проверяет namespace каждого veth-peer.' \
        '' \
        'down откажет при чужом inode, интерфейсе, потере метки или работающем процессе.' \
        'READY требует полного состава links; в partial setup допустима лишь целиком отсутствующая veth-пара.' \
        'Peer вне ожидаемого owned namespace или неизвестный NSID запрещает любое удаление.' \
        'Закройте учебные команды сами: скрипт не отправляет kill и не делает flush ruleset.' \
        'После ошибки up сохраняются manifest и созданные namespace для проверки/down.' \
        'Между netns add и записью inode возможен сбой: down тогда консервативно откажет.' \
        'Не подделывайте manifest. Если ownership проверить нельзя, откатите снимок одноразовой VM.'
}

die() { printf 'Ошибка: %s\n' "$*" >&2; exit 1; }
note() { printf '%s\n' "$*"; }

known_name() {
    case "$1" in nl7-client|nl7-peer|nl7-router|nl7-server) return 0;; *) return 1;; esac
}

exists() { [[ -e "$1" || -L "$1" ]]; }

require_commands() {
    local cmd
    for cmd in ip sysctl stat flock mkdir chmod rm rmdir sleep python3; do
        command -v "$cmd" >/dev/null 2>&1 || die "Нужна команда $cmd; установите её в учебной VM самостоятельно."
    done
}

require_mutation_permission() {
    [[ $CONFIRMED == 1 ]] || die 'Нужен явный флаг --inside-disposable-vm. Ничего не изменено.'
    [[ $EUID == 0 ]] || die 'Для up/down нужен UID 0 внутри одноразовой VM. Ничего не изменено.'
}

preflight_names() {
    local ns
    # Проверяются и namespace handles, и per-namespace конфигурация ip netns exec.
    for ns in "${NAMES[@]}"; do
        exists "$NETNS_DIR/$ns" && die "Имя $ns уже занято. Чужие namespace не изменяются."
        exists "/etc/netns/$ns" && die "Уже есть /etc/netns/$ns; чужая конфигурация не используется."
    done
    return 0
}

check() {
    local cmd ns missing=0
    note 'Read-only проверка: сетевые команды и создание файлов не выполняются.'
    for cmd in ip sysctl stat flock mkdir chmod rm rmdir sleep python3; do
        if command -v "$cmd" >/dev/null 2>&1; then
            printf 'dependency %-8s OK\n' "$cmd"
        else
            printf 'dependency %-8s MISSING\n' "$cmd"
            missing=1
        fi
    done
    printf 'UID=%s; confirmation=%s (не доказательство VM)\n' "$EUID" "$CONFIRMED"
    if command -v nft >/dev/null 2>&1; then
        note 'optional nft: найден; up/down его не вызывают.'
    else
        note 'optional nft: отсутствует; для базовой топологии не нужен.'
    fi
    exists "$STATE_DIR" && note "State уже существует: $STATE_DIR (up повторно откажет)."
    for ns in "${NAMES[@]}"; do
        if exists "$NETNS_DIR/$ns" || exists "/etc/netns/$ns"; then
            printf '%s: имя/config занято; требуется status.\n' "$ns"
        else
            printf '%s: имя/config свободно.\n' "$ns"
        fi
    done
    note 'Capabilities, kernel modules и реальная VM здесь НЕ проверяются и не обещаются.'
    return "$missing"
}

validate_state_files() {
    local path
    [[ -d "$STATE_DIR" && ! -L "$STATE_DIR" ]] || die "State отсутствует или не является обычным каталогом: $STATE_DIR"
    [[ $(stat -c '%u:%a' -- "$STATE_DIR") == 0:700 ]] || die 'State должен принадлежать root с mode 0700.'
    for path in "$MANIFEST" "$STATE_DIR/lock"; do
        [[ -f "$path" && ! -L "$path" ]] || die "Нет обычного файла ownership: $path"
        [[ $(stat -c '%u:%a' -- "$path") == 0:600 ]] || die "Некорректные owner/mode: $path"
    done
    # Не удаляем неизвестные файлы даже из своего каталога.
    shopt -s nullglob dotglob
    for path in "$STATE_DIR"/*; do
        case "$path" in "$MANIFEST"|"$STATE_DIR/lock") ;; *) die "Неизвестный файл state: $path";; esac
    done
    shopt -u nullglob dotglob
}

read_manifest() {
    local kind first second extra format=0 count=0
    OWNED=()
    TOKEN=''
    READY=0
    while IFS=' ' read -r kind first second extra || [[ -n "$kind$first$second$extra" ]]; do
        [[ -z "$extra" ]] || die 'Повреждён manifest: лишние поля.'
        case "$kind" in
            FORMAT)
                [[ $format == 0 && "$first" == 1 && -z "$second" ]] || die 'Неизвестный/повторный FORMAT.'
                format=1
                ;;
            TOKEN)
                [[ $format == 1 && -z "$TOKEN" && -z "$second" && "$first" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || die 'Некорректный TOKEN.'
                TOKEN=$first
                ;;
            NS)
                known_name "$first" || die 'Manifest содержит неизвестный namespace.'
                [[ -n "$TOKEN" && $READY == 0 && -z ${OWNED[$first]+yes} && "$second" =~ ^[0-9]+:[0-9]+$ ]] || die 'Некорректная/повторная запись NS.'
                OWNED[$first]=$second
                count=$((count + 1))
                ;;
            READY)
                [[ -n "$TOKEN" && $READY == 0 && -z "$first" && -z "$second" && $count == 4 ]] || die 'Некорректная запись READY.'
                READY=1
                ;;
            *) die 'Повреждён manifest: неизвестная/пустая запись.';;
        esac
    done < "$MANIFEST"
    [[ $format == 1 && -n "$TOKEN" ]] || die 'Manifest не содержит FORMAT/TOKEN.'
}

verify_namespace_identity() {
    local ns=$1 actual
    [[ ! -L "$NETNS_DIR/$ns" && -f "$NETNS_DIR/$ns" ]] || die "Нет обычного namespace handle: $ns"
    actual=$(stat -Lc '%d:%i' -- "$NETNS_DIR/$ns")
    [[ "$actual" == "${OWNED[$ns]}" ]] || die "Чужой/replaced inode у $ns: отказ без удаления."
}

verify_cleanup_targets() {
    local ns pids
    local -a present=()
    # Сначала проверяются ВСЕ имена; при любом сомнении удаления ещё не было.
    for ns in "${NAMES[@]}"; do
        if [[ -n ${OWNED[$ns]+yes} ]]; then
            if exists "$NETNS_DIR/$ns"; then
                verify_namespace_identity "$ns"
                pids=$(ip netns pids "$ns") || die "Невозможно проверить PIDs в $ns."
                [[ -z "$pids" ]] || die "В $ns работают процессы ($pids). Завершите свои команды сами; kill не выполняется."
                present+=("$ns")
            fi
        elif exists "$NETNS_DIR/$ns"; then
            die "$ns существует, но не записан в ownership manifest. Ничего не удалено."
        fi
    done
    # Только read-only JSON-команды. Если veth-peer перенесли наружу, удаление
    # оставшегося конца тоже удалило бы внешний peer: до удаления проверяем ОБА.
    # ifindex/link_index локальны namespace; одних совпавших чисел недостаточно.
    python3 - "$TOKEN" "$READY" "${present[@]}" <<'PY'
import json
import subprocess
import sys


def refuse(message):
    raise ValueError(message)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def ip_json(namespace, *arguments):
    result = subprocess.run(["ip", "-j", "-n", namespace, *arguments],
                            capture_output=True, text=True, timeout=5, check=False)
    if result.returncode != 0:
        refuse(f"Не прочитать inventory/NSID в {namespace}: {result.stderr.strip()}")
    value = json.loads(result.stdout)
    if not isinstance(value, list):
        refuse(f"Неизвестный JSON-формат iproute2 в {namespace}")
    return value


def verify():
    token, ready = sys.argv[1:3]
    present = set(sys.argv[3:])
    expected = {
        "nl7-client": {"lo": "loopback", "eth0": "veth"},
        "nl7-peer": {"lo": "loopback", "eth0": "veth"},
        "nl7-router": {"lo": "loopback", "br-lan": "bridge", "lan-client": "veth",
                       "lan-peer": "veth", "wan0": "veth"},
        "nl7-server": {"lo": "loopback", "eth0": "veth"},
    }
    pairs = [("nl7-router", "lan-client", "nl7-client", "eth0"),
             ("nl7-router", "lan-peer", "nl7-peer", "eth0"),
             ("nl7-router", "wan0", "nl7-server", "eth0")]
    if ready not in {"0", "1"} or not present <= expected.keys():
        refuse("Некорректные входные параметры inventory")
    if ready == "1" and present != expected.keys():
        refuse("READY: отсутствует ожидаемый owned namespace")
    inventory = {}
    for namespace in sorted(present):
        links, indexes = {}, set()
        for row in ip_json(namespace, "-d", "link", "show"):
            if not isinstance(row, dict):
                refuse(f"Неизвестная запись link в {namespace}")
            name, index = row.get("ifname"), row.get("ifindex")
            if not isinstance(name, str) or name not in expected[namespace]:
                refuse(f"Неизвестный интерфейс {namespace}/{name}")
            if name in links or not integer(index, 1) or index in indexes:
                refuse(f"Повторный/неизвестный ifindex/ifname в {namespace}")
            kind = expected[namespace][name]
            if name == "lo":
                if row.get("link_type") != "loopback":
                    refuse(f"Неожиданный тип loopback в {namespace}")
            else:
                if row.get("ifalias") != "cpp-course-netlab7:" + token:
                    refuse(f"Нет ownership-метки у {namespace}/{name}")
                info = row.get("linkinfo")
                if not isinstance(info, dict) or info.get("info_kind") != kind:
                    refuse(f"Неожиданный тип {namespace}/{name}; ожидался {kind}")
            links[name] = row
            indexes.add(index)
        if "lo" not in links or (ready == "1" and links.keys() != expected[namespace].keys()):
            refuse(f"READY/inventory: отсутствует ожидаемый интерфейс в {namespace}")
        inventory[namespace] = links
    nsid_cache = {}

    def verify_peer(namespace, device, row, peer_namespace, peer_device, peer):
        nsid = row.get("link_netnsid")
        if not integer(nsid) or not integer(row.get("link_index"), 1):
            refuse(f"Неизвестный peer NSID/iflink у {namespace}/{device}")
        key = (namespace, nsid)
        if key not in nsid_cache:
            records = ip_json(namespace, "netns", "list-id", "nsid", str(nsid))
            if len(records) != 1 or not isinstance(records[0], dict):
                refuse(f"Неизвестный NSID mapping в {namespace}")
            mapping = records[0]
            if type(mapping.get("nsid")) is not int or mapping["nsid"] != nsid or mapping.get("deleted"):
                refuse(f"Некорректный NSID mapping в {namespace}")
            nsid_cache[key] = mapping.get("name")
        if nsid_cache[key] != peer_namespace:
            refuse(f"Внешний/unmapped peer у {namespace}/{device}; ожидался {peer_namespace}/{peer_device}")
        if row["link_index"] != peer["ifindex"] or peer.get("link_index") != row["ifindex"]:
            refuse(f"Не взаимная veth-пара {namespace}/{device} и {peer_namespace}/{peer_device}")

    for left_ns, left_dev, right_ns, right_dev in pairs:
        left = inventory.get(left_ns, {}).get(left_dev)
        right = inventory.get(right_ns, {}).get(right_dev)
        if left is None and right is None and ready == "0":
            continue  # Partial setup: допустима лишь целиком отсутствующая пара.
        if left is None or right is None:
            refuse(f"Отсутствует проверенный peer пары {left_ns}/{left_dev} ↔ {right_ns}/{right_dev}")
        verify_peer(left_ns, left_dev, left, right_ns, right_dev, right)
        verify_peer(right_ns, right_dev, right, left_ns, left_dev, left)


try:
    verify()
except (ValueError, OSError, subprocess.SubprocessError) as error:
    print(f"Ошибка: {error}. Отказ до удаления; при сомнении откатите снимок VM.", file=sys.stderr)
    sys.exit(1)
PY
}

create_namespace() {
    local ns=$1 identity
    ip netns add "$ns"
    identity=$(stat -Lc '%d:%i' -- "$NETNS_DIR/$ns")
    [[ "$identity" =~ ^[0-9]+:[0-9]+$ ]] || die "Не удалось сохранить inode $ns."
    # Не source/eval: только строго ограниченные имена и числовой inode.
    printf 'NS %s %s\n' "$ns" "$identity" >> "$MANIFEST"
    OWNED[$ns]=$identity
    ip -n "$ns" link set dev lo up
    # Только per-network-namespace sysctl, никогда не sysctl хоста.
    ip netns exec "$ns" sysctl -q -w \
        net.ipv6.conf.all.disable_ipv6=0 net.ipv6.conf.default.disable_ipv6=0 \
        net.ipv6.conf.all.accept_ra=0 net.ipv6.conf.default.accept_ra=0 \
        net.ipv6.conf.all.autoconf=0 net.ipv6.conf.default.autoconf=0 \
        net.ipv6.conf.all.accept_dad=1 net.ipv6.conf.default.accept_dad=1
}

tag_topology() {
    local tag=$1 device ns
    for device in br-lan lan-client lan-peer wan0; do
        ip -n nl7-router link set dev "$device" alias "$tag"
    done
    for ns in nl7-client nl7-peer nl7-server; do
        ip -n "$ns" link set dev eth0 alias "$tag"
    done
}

wait_for_dad() {
    local attempt ns addresses pending
    for attempt in {1..50}; do
        pending=0
        for ns in "${NAMES[@]}"; do
            addresses=$(ip -n "$ns" -6 -o address show) || die "Не прочитать IPv6-адреса $ns."
            [[ " $addresses " != *' dadfailed '* ]] || die "IPv6 DAD failure в $ns; стенд НЕ объявлен готовым."
            [[ " $addresses " != *' tentative '* ]] || pending=1
        done
        [[ $pending == 0 ]] && return 0
        sleep 0.1
    done
    die 'IPv6 DAD не завершился за 5 секунд; проверьте status. READY не записан.'
}

on_exit() {
    local result=$?
    if [[ $result != 0 && $STATE_CREATED == 1 ]]; then
        printf 'up прерван. Созданные ресурсы НЕ удаляются вслепую.\nПроверьте status; затем внутри той же VM: bash network_lab.sh down --inside-disposable-vm\nOwnership сохранён в %s.\nСбой между netns add и записью inode может вызвать консервативный отказ down.\nНе подделывайте manifest: если ownership проверить нельзя, откатите снимок одноразовой VM.\n' "$STATE_DIR" >&2
    fi
}

up() {
    local ns tag
    require_mutation_permission
    require_commands
    exists "$STATE_DIR" && die "Уже есть $STATE_DIR. Проверьте status и выполните down внутри этой VM."
    preflight_names
    [[ -r /proc/sys/kernel/random/uuid ]] || die 'Нет источника ownership token.'
    IFS= read -r TOKEN < /proc/sys/kernel/random/uuid
    [[ "$TOKEN" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || die 'Не удалось прочитать UUID.'
    mkdir -m 0700 -- "$STATE_DIR"
    STATE_CREATED=1
    trap on_exit EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    printf 'FORMAT 1\nTOKEN %s\n' "$TOKEN" > "$MANIFEST"
    : > "$STATE_DIR/lock"
    chmod 0600 -- "$MANIFEST" "$STATE_DIR/lock"
    exec 9< "$STATE_DIR/lock"
    flock -n 9 || die 'Другая операция со стендом уже выполняется.'
    for ns in "${NAMES[@]}"; do create_namespace "$ns"; done
    tag="cpp-course-netlab7:$TOKEN"

    # Оба конца каждой пары создаются сразу ВНУТРИ namespace; host link не нужен.
    ip -n nl7-router link add name br-lan alias "$tag" type bridge stp_state 0
    ip -n nl7-router link add name lan-client type veth peer name eth0 netns nl7-client
    ip -n nl7-router link add name lan-peer type veth peer name eth0 netns nl7-peer
    ip -n nl7-router link add name wan0 type veth peer name eth0 netns nl7-server
    # Метку назначаем каждому уже созданному концу явно в его namespace.
    # Нельзя полагаться на обработку alias во вложенных параметрах peer.
    tag_topology "$tag"
    ip -n nl7-router link set dev lan-client master br-lan
    ip -n nl7-router link set dev lan-peer master br-lan
    ip -n nl7-router link set dev lan-client up
    ip -n nl7-router link set dev lan-peer up
    ip -n nl7-router link set dev br-lan up
    ip -n nl7-router link set dev wan0 up
    for ns in nl7-client nl7-peer nl7-server; do ip -n "$ns" link set dev eth0 up; done

    ip -n nl7-router address add 192.0.2.1/24 dev br-lan
    ip -n nl7-router address add 198.51.100.1/24 dev wan0
    ip -n nl7-router -6 address add 2001:db8:7:1::1/64 dev br-lan
    ip -n nl7-router -6 address add 2001:db8:7:2::1/64 dev wan0
    ip -n nl7-client address add 192.0.2.10/24 dev eth0
    ip -n nl7-client -6 address add 2001:db8:7:1::10/64 dev eth0
    ip -n nl7-peer address add 192.0.2.11/24 dev eth0
    ip -n nl7-peer -6 address add 2001:db8:7:1::11/64 dev eth0
    ip -n nl7-server address add 198.51.100.10/24 dev eth0
    ip -n nl7-server -6 address add 2001:db8:7:2::10/64 dev eth0

    # Эти default routes существуют только в трёх учебных namespace.
    for ns in nl7-client nl7-peer; do
        ip -n "$ns" route add default via 192.0.2.1 dev eth0
        ip -n "$ns" -6 route add default via 2001:db8:7:1::1 dev eth0
    done
    ip -n nl7-server route add default via 198.51.100.1 dev eth0
    ip -n nl7-server -6 route add default via 2001:db8:7:2::1 dev eth0
    ip netns exec nl7-router sysctl -q -w net.ipv4.ip_forward=1 net.ipv6.conf.all.forwarding=1
    wait_for_dad
    printf 'READY\n' >> "$MANIFEST"
    READY=1
    note 'READY: статическая IPv4/IPv6-топология создана; DAD завершён. Это не проверка ping/TCP.'
    note 'Host default route, firewall, DNS и sysctl не менялись. NAT и службы не включались.'
    note 'Далее: bash network_lab.sh status. По окончании: down --inside-disposable-vm.'
}

status() {
    local ns
    command -v stat >/dev/null 2>&1 || die 'Для status нужна команда stat.'
    if ! exists "$STATE_DIR"; then
        note 'Ownership state отсутствует. Ничего не изменено.'
        for ns in "${NAMES[@]}"; do exists "$NETNS_DIR/$ns" && note "$ns существует БЕЗ ownership этого скрипта."; done
        return 0
    fi
    if [[ $EUID != 0 ]]; then
        note 'Ownership state существует; прочитать root-only manifest может UID 0.'
        note 'status ничего не меняет. Для подробностей выполните его с root внутри учебной VM.'
        return 0
    fi
    validate_state_files
    read_manifest
    printf 'manifest READY=%s (0 = незавершённый up); state=%s\n' "$READY" "$STATE_DIR"
    for ns in "${NAMES[@]}"; do
        if [[ -z ${OWNED[$ns]+yes} ]]; then
            note "$ns: не создан/не записан."
            continue
        fi
        if ! exists "$NETNS_DIR/$ns"; then note "$ns: handle уже отсутствует."; continue; fi
        verify_namespace_identity "$ns"
        note "[$ns] inode=${OWNED[$ns]}"
        if command -v ip >/dev/null 2>&1; then
            ip -n "$ns" -brief address show
            ip -n "$ns" -4 route show
            ip -n "$ns" -6 route show
        fi
    done
}

down() {
    local ns
    require_mutation_permission
    require_commands
    if ! exists "$STATE_DIR"; then
        for ns in "${NAMES[@]}"; do exists "$NETNS_DIR/$ns" && die "$ns есть без ownership; отказ без удаления."; done
        note 'Стенд уже отсутствует; ничего не удалено.'
        return 0
    fi
    validate_state_files
    exec 9< "$STATE_DIR/lock"
    flock -n 9 || die 'Другая операция со стендом уже выполняется.'
    read_manifest
    verify_cleanup_targets
    # Никаких glob/delete-all: только четыре известных имени и проверенные inode.
    for ns in nl7-client nl7-peer nl7-server nl7-router; do
        if [[ -n ${OWNED[$ns]+yes} ]] && exists "$NETNS_DIR/$ns"; then
            # Повторная проверка сокращает окно ошибки; другой root не должен параллельно менять VM.
            verify_namespace_identity "$ns"
            ip netns delete "$ns"
        fi
    done
    rm -- "$MANIFEST" "$STATE_DIR/lock"
    rmdir -- "$STATE_DIR"
    note 'Удалены только namespace стенда, их виртуальные links/маршруты/rules и его ownership state.'
    note 'Эти учебные сетевые настройки не восстанавливаются; для нового опыта выполните up в VM.'
}

main() {
    local action=help arg
    if [[ $# -gt 0 && "$1" != --inside-disposable-vm ]]; then action=$1; shift; fi
    for arg in "$@"; do
        case "$arg" in
            --inside-disposable-vm) [[ $CONFIRMED == 0 ]] || die 'Флаг подтверждения указан дважды.'; CONFIRMED=1;;
            *) die "Неизвестный аргумент: $arg";;
        esac
    done
    case "$action" in
        help|-h|--help) usage;;
        check) check;;
        status) status;;
        up) up;;
        down) down;;
        *) die "Неизвестная команда: $action. Используйте help.";;
    esac
}

main "$@"
