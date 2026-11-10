"""Manages the hub connection and communication."""
import re
import time
import asyncio
import serial_asyncio_fast as serial_asyncio
import socket

from typing import cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN,
    NAME,
    VERSION,
    LOGGER,
    SMART_HOME_1,
    SMART_HOME_2,
    NEW_BINARY_SENSOR,
    NEW_CLIMATE,
    NEW_FAN,
    NEW_LIGHT,
    NEW_SENSOR,
    NEW_SWITCH,
)
from .center import BestinCenterAPI
from .controller import BestinController
from .iparkapp import BestinIparkAppAPI
from .errors import BestinIparkAppError, IparkAppConnectionError
from .iparkapp_const import CONF_IPARKAPP_SITE, SMART_HOME_APP
from .until import check_ip_or_serial


class ConnectionManager:
    """Handles hub connections."""
    
    def __init__(self, conn_str: str) -> None:
        """Initialize the ConnectionManager."""
        self.conn_str = conn_str
        self.is_serial = False
        self.is_socket = False
        self.reader: asyncio.StreamReader = None
        self.writer: asyncio.StreamWriter = None
        self.reconnect_attempts: int = 0
        self.last_reconnect_attempt: float = None
        self.next_attempt_time: float = None
        # 받기와 보내기 작업이 동시에 다시 연결하지 않도록 합니다.
        # Keeps the receive and send tasks from reconnecting at the same time.
        self._reconnect_lock = asyncio.Lock()

        self.chunk_size = 64
        # RS-485 버스는 쉬지 않고 패킷을 보내므로, 이만큼 조용하면 TCP 연결이
        # 죽은 것입니다 (반쯤 끊긴 연결). laz- 의 포크에서 가져온 생각입니다.
        # The RS-485 bus never goes quiet, so this much silence means the TCP
        # session is dead (half-open). Idea from laz-'s fork.
        self.read_timeout = 30.0
        self.constant_packet_length = 10
        self._parse_conn_str()

    def _parse_conn_str(self) -> bool:
        """Parse the connection string to determine connection type."""
        if re.match(r"COM\d+|/dev/tty\w+", self.conn_str):
            self.is_serial = True
        elif re.match(r"\d+\.\d+\.\d+\.\d+:\d+", self.conn_str):
            self.is_socket = True
        else:
            raise ValueError("Invalid connection string")

    async def connect(self, timeout: int = 5) -> bool:
        """Establish a connection.

        실패하면 기록만 하고 False 를 돌려줍니다. 예전에는 여기서 reconnect()
        를 불렀고, reconnect() 가 다시 connect() 를 불러 서로 되부르며 돌았습니다.
        다시 시도는 받기 루프가 맡습니다.
        On failure it logs and returns False. It used to call reconnect(),
        which called connect() again, so the two recursed into each other.
        Retrying is the receive loop's job.
        """
        try:
            if self.is_serial:
                await self._connect_serial()
            elif self.is_socket:
                await self._connect_socket()
        except Exception as e:  # noqa: BLE001
            LOGGER.error(f"Connection failed: {e!r}")
            await self._close_writer()
            return False
        LOGGER.info("Connection established successfully.")
        return True

    async def _connect_serial(self) -> None:
        """Establish a serial connection."""
        self.reader, self.writer = await serial_asyncio.open_serial_connection(
            url=self.conn_str, baudrate=9600
        )
        LOGGER.info(f"Serial connection established on {self.conn_str}")

    async def _connect_socket(self) -> None:
        """Establish a socket connection."""
        host, port = self.conn_str.split(":")
        self.reader, self.writer = await asyncio.open_connection(host, int(port))
        LOGGER.info(f"Socket connection established to {host}:{port}")

    def is_connected(self) -> bool:
        """Check if the connection is active."""
        try:
            if self.writer is None:
                return False
            if self.is_serial:
                return not self.writer.transport.is_closing()
            elif self.is_socket:
                # 예전에는 writer 가 있기만 하면 연결된 것으로 봤습니다.
                # Used to count any writer as connected, even a closed one.
                return not self.writer.is_closing()
            return False
        except Exception:
            return False

    async def _close_writer(self) -> None:
        """Close the writer and forget it, so is_connected() turns False."""
        writer, self.writer = self.writer, None
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    async def reconnect(self) -> bool:
        """Attempt to reconnect with exponential backoff.

        잠금으로 한 번에 하나만 돕니다. 대기 시간 전이면 바로 False 를
        돌려주므로 부르는 쪽은 잠깐 쉬었다가 다시 부르면 됩니다.
        One at a time under a lock. Before the backoff time is up it returns
        False at once, so callers just pause and call again.
        """
        failed_writer = self.writer
        async with self._reconnect_lock:
            if self.writer is not failed_writer and self.is_connected():
                # 기다리는 동안 다른 작업이 이미 다시 연결했습니다. 새 연결을
                # 닫으면 안 됩니다.
                # Another task reconnected while this one waited for the
                # lock; closing that fresh connection would undo it.
                return True
            await self._close_writer()

            current_time = time.time()
            if self.next_attempt_time and current_time < self.next_attempt_time:
                return False

            self.reconnect_attempts += 1
            delay = min(2 ** self.reconnect_attempts, 60) if self.last_reconnect_attempt else 1
            self.last_reconnect_attempt = current_time
            self.next_attempt_time = current_time + delay
            LOGGER.info(f"Reconnection attempt {self.reconnect_attempts} after {delay} seconds delay...")

            await asyncio.sleep(delay)
            if await self.connect() and self.is_connected():
                LOGGER.info(f"Successfully reconnected on attempt {self.reconnect_attempts}.")
                self.reconnect_attempts = 0
                self.last_reconnect_attempt = None
                self.next_attempt_time = None
                return True
            return False

    async def send(self, packet: bytearray, interval: int) -> None:
        """Send a packet."""
        try:
            self.writer.write(packet)
            await self.writer.drain()
            await asyncio.sleep(interval)
        except Exception as e:
            LOGGER.error(f"Failed to send packet data: {e}")
            await self.reconnect()

    async def receive(self, size: int = 64) -> bytes | None:
        """Receive data."""
        try:
            if self.chunk_size == size:
                return await asyncio.wait_for(self._receive_socket(), timeout=self.read_timeout)
            data = await asyncio.wait_for(self.reader.read(size), timeout=self.read_timeout)
            if not data:
                raise ConnectionError("Connection closed by remote")
            return data
        except asyncio.TimeoutError:
            if self.is_socket:
                LOGGER.warning(
                    "No RS-485 data for %.0f s, reconnecting", self.read_timeout
                )
                await self.reconnect()
            return None
        except Exception as e:
            LOGGER.error(f"Failed to receive packet data: {e!r}")
            await self.reconnect()
            return None

    async def _receive_socket(self) -> bytes:
        """Receive data from a socket connection."""
        
        async def recv_exactly(n):
            data = b''
            while len(data) < n:
                chunk = await self.reader.read(n - len(data))
                if not chunk:
                    raise socket.error("Connection closed")
                data += chunk
            return data

        packet = b''
        try:
            while True:
                while True:
                    initial_data = await self.reader.read(1)
                    if not initial_data:
                        # 상대가 연결을 닫았습니다. 예전에는 빈 값을 돌려줘서
                        # 다시 연결하지 않고 끝없이 돌았습니다 (laz- 의 포크).
                        # The far end closed the connection. Returning b''
                        # here used to spin forever with no reconnect
                        # (found in laz-'s fork).
                        raise socket.error("Connection closed by remote")
                    packet += initial_data
                    if 0x02 in packet:
                        start_index = packet.index(0x02)
                        packet = packet[start_index:]
                        break

                packet += await recv_exactly(3 - len(packet))

                if (
                    packet[1] not in [0x28, 0x31, 0x32, 0x41, 0x42, 0x61, 0xD1]
                    and packet[1] & 0xF0 != 0x50   # For AIO (0x51-0x55)
                    and packet[1] & 0x30 != 0x30   # For Gen2 (0x3F, 0x31-0x36)
                ):
                    return b''

                # 0x32 는 두 번째 가스 밸브로, 0x31 과 같은 10바이트 고정
                # 길이입니다. 모르면 세 번째 바이트 (0x80 = 128) 를 길이로 읽어
                # 뒤따르는 패킷 여럿을 삼켰습니다 (laz- 의 포크).
                # 0x32 is a second gas valve with the same fixed 10-byte
                # format as 0x31. Unknown, its third byte (0x80 = 128) was read
                # as a length and swallowed the packets after it (laz-'s fork).
                if (
                    (packet[1] in (0x31, 0x32) and packet[2] in [0x00, 0x01, 0x02, 0x80, 0x81, 0x82])
                    or packet[1] == 0x61
                    or packet[1] == 0x17  # For AIO
                ):
                    packet_length = self.constant_packet_length
                else:
                    packet_length = packet[2]
                
                if packet_length <= 0:
                    #LOGGER.error(f"Invalid packet length in packet: {packet.hex()}")
                    return b''

                packet += await recv_exactly(packet_length - len(packet))
                
                if len(packet) >= packet_length:
                    return packet[:packet_length]

        except socket.error as e:
            # receive() 가 다시 연결합니다. 여기서도 하면 두 번 하게 됩니다.
            # receive() reconnects; doing it here too would do it twice.
            LOGGER.error(f"Socket error: {e}")
            raise

        return b''

    async def close(self) -> None:
        """Close the connection."""
        if self.writer:
            LOGGER.info("Connection closed.")
            await self._close_writer()


class BestinHub:
    """Represents a Bestin Hub for managing smart home devices."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the BestinHub."""
        self.hass = hass
        self.entry = entry
        self.api: BestinCenterAPI | BestinController | BestinIparkAppAPI = None
        self.connection: ConnectionManager = None
        # 설정 단계의 연결 확인은 항목 없이 (entry=None) 허브를 만듭니다.
        # v1.4.22 는 여기서 AttributeError 를 내서 RS-485 설정이 '알 수 없는
        # 오류' 로 끝났습니다 (이슈 #4).
        # The config flow's connection test builds a hub with entry=None.
        # v1.4.22 raised AttributeError here, and RS-485 setup ended in
        # "unknown error" (issue #4).
        saved_mode = entry.data.get("gateway_mode") if entry else None
        if saved_mode and isinstance(saved_mode, (list, tuple)) and len(saved_mode) == 2:
            self.gateway_mode = tuple(saved_mode)
        else:
            self.gateway_mode = None
        self.entity_groups: dict[str, set[str]] = {}
        self.entity_to_id: dict[str, str] = {}
        # 허브 디바이스의 레지스트리 id (__init__.py 에서 설정).
        # Registry id of the hub device, set in __init__.py.
        self.device_id: str | None = None

    @staticmethod
    def get_hub(hass: HomeAssistant, entry: ConfigEntry) -> BestinCenterAPI | BestinController:
        """Get the hub instance."""
        return hass.data[DOMAIN][entry.entry_id]

    @property
    def hub_id(self) -> str:
        """Get the hub ID."""
        return cast(str, self.entry.unique_id)

    @property
    def port(self) -> int:
        """Get the port number."""
        return cast(int, self.entry.data.get(CONF_PORT))

    @property
    def gw_type(self) -> str:
        """Get the gateway type."""
        return cast(str, self.gateway_mode[0])
    
    @property
    def available(self) -> bool:
        """Check if the hub is available."""
        if self.connection:
            return self.connection.is_connected()
        return True
    
    @property
    def model(self) -> str:
        """Get the model of the hub."""
        return DOMAIN

    @property
    def name(self) -> str:
        """Get the name of the hub."""
        return NAME
    
    @property
    def sw_version(self) -> str:
        """Get the software version of the hub."""
        return VERSION

    @property
    def cntr_version(self) -> str:
        """Get the controller version."""
        if CONF_IPARKAPP_SITE in self.entry.data:
            return SMART_HOME_APP
        if CONF_USERNAME in self.entry.data:
            return SMART_HOME_1
        return SMART_HOME_2
    
    @property
    def is_polling(self) -> bool:
        """Check if the hub is in polling mode."""
        if check_ip_or_serial(self.hub_id):
            return False
        else:
            return True

    @property
    def wp_version(self) -> str:
        """Get the WP version."""
        if check_ip_or_serial(self.hub_id):
            return f"{self.gw_type}-generation"
        else:
            return self.cntr_version

    def conn_str(self, host: str | None, port: int | None) -> str:
        """Generate the connection string."""
        # 항목이 있으면 저장된 값을, 설정 단계 (entry=None) 에서는 입력값을 씁니다.
        # Saved values when there is an entry; the typed ones during setup.
        if self.entry is not None:
            host, port = self.hub_id, self.port
        if not re.match(r"/dev/tty(USB|AMA)\d+", host):
            return f"{host}:{port}"
        return host
    
    async def determine_gateway_mode(self) -> None:
        """Determine the gateway mode."""
        chunk_storage: list = []
        aio_data: dict = {}
        gen2_data: dict = {}
        try:
            while len(b''.join(chunk_storage)) < 1024:
                received_data = await asyncio.wait_for(
                    self.connection._receive_socket(), timeout=10.0
                )
                if not received_data:
                    break
                chunk_storage.append(received_data)

            for chunk in chunk_storage:
                if len(chunk) < 4:
                    raise ValueError(f"Chunk length is too short: length={len(chunk)}, chunk={chunk.hex()}")     
                chunk_length = chunk[2]
                room_byte = chunk[1]
                command_byte = chunk[3]

                LOGGER.debug(
                    "Received chunk: length=%d, room_byte=%s, command_byte=%s, hex=%s",
                    chunk_length, hex(room_byte), hex(command_byte), chunk.hex()
                )
                if (chunk_length in [20, 22] and command_byte in [0x91, 0xB2]):
                    aio_data[room_byte] = command_byte
                elif (chunk_length in [59, 72, 98, 150] and command_byte == 0x91):
                    gen2_data[room_byte] = command_byte

            if aio_data:
                self.gateway_mode = ("AIO", aio_data)
                LOGGER.debug(f"AIO mode set with data: {aio_data}")
            elif gen2_data:
                self.gateway_mode = ("Gen2", gen2_data)
                LOGGER.debug(f"Gen2 mode set with data: {gen2_data}")
            else:
                self.gateway_mode = ("General", None)
                LOGGER.debug("General mode set")
        except TimeoutError:
            LOGGER.warning(
                "Timed out waiting for gateway data, defaulting to General mode"
            )
            self.gateway_mode = ("General", None)
        except OSError:
            # 연결이 끊겼습니다. 설정이 나중에 다시 시도하도록 그대로 올립니다.
            # The connection dropped; pass it up so setup retries later.
            raise
        except Exception as e:
            problematic_packet = locals().get("received_data", None)
            raise RuntimeError(
                f"Error during gateway mode determination: {e}. "
                f"Problematic packet: {problematic_packet.hex() if problematic_packet else 'None'}"
            )

    @callback
    def async_signal_new_device(self, device_type: str) -> str:
        """Generate a signal for a new device."""
        new_device = {
            NEW_BINARY_SENSOR: "bestin_new_binary_sensor",
            NEW_CLIMATE: "bestin_new_climate",
            NEW_FAN: "bestin_new_fan",
            NEW_LIGHT: "bestin_new_light",
            NEW_SENSOR: "bestin_new_sensor",
            NEW_SWITCH: "bestin_new_switch",
        }
        return f"{new_device[device_type]}_{self.hub_id}"

    @callback
    def async_add_device_callback(
        self, device_type: str, device=None, force: bool = False
    ) -> None:
        """Add a new device callback."""
        domain = device.domain
        unique_id = device.unique_id
        device_info = device.info
        
        if (
            unique_id in self.entity_groups.get(domain, set()) or
            device_info.device_id in self.entity_to_id
        ):
            return
        
        args = []
        if device is not None and not isinstance(device, list):
            args.append([device])

        async_dispatcher_send(
            self.hass,
            self.async_signal_new_device(device_type),
            *args,
        )
    
    async def connect(self, host: str = None, port: int = None) -> bool:
        """Connect to the hub."""
        if not self.connection or not self.available:
            self.connection = ConnectionManager(self.conn_str(host, port))
        else:
            await self.connection.close()

        await self.connection.connect()
        return self.available
    
    async def async_close(self) -> None:
        """Close the hub connection."""
        if self.api:
            await self.api.stop()
        if self.connection and self.available:
            await self.connection.close()
        if self.gateway_mode:
            self.gateway_mode = None

    async def shutdown(self, event: Event) -> None:
        """Shutdown the hub on EVENT_HOMEASSISTANT_STOP.

        ``@callback`` 이 붙어 있었지만 이 함수는 코루틴입니다. HA 는
        ``iscoroutinefunction`` 을 먼저 검사하므로 실제 동작에는 문제가 없었으나,
        데코레이터의 의미('이벤트 루프에서 동기 실행해도 안전')와 정반대라
        오해를 부릅니다. 이 경로는 듀티 사이클 원복(release)을 await 해야 하므로
        더더욱 코루틴이어야 합니다.

        This used to carry ``@callback``, which asserts the opposite of what
        is true here — the decorator means "safe to run synchronously in the
        event loop", and this is a coroutine that must be awaited (it drives
        the duty-cycle hand-back). It worked only because HA checks
        ``iscoroutinefunction`` before ``is_callback``.
        """
        await self.async_close()
    
    async def async_initialize_serial(self) -> None:
        """Initialize the serial connection."""
        try:
            if self.gateway_mode is None:
                await self.determine_gateway_mode()

            stored_mode = self.entry.data.get("gateway_mode")
            if stored_mode is None or tuple(stored_mode) != self.gateway_mode:
                self.hass.config_entries.async_update_entry(
                    entry=self.entry,
                    data={**self.entry.data, "gateway_mode": list(self.gateway_mode)},
                )
            self.api = BestinController(
                self.hass,
                self.entry,
                self.entity_groups,
                self.hub_id,
                self.connection,
                self.async_add_device_callback,
            )
            await self.api.start()
        except OSError:
            self.api = None
            raise
        except Exception as ex:
            self.api = None
            raise RuntimeError(
                f"Failed to initialize Bestin hub. Host: {self.hub_id}, Mode: {self.gateway_mode}. "
                f"Error: {str(ex)}"
            )

    async def async_initialize_center(self) -> None:
        """Initialize the center connection."""
        try:
            self.api = BestinCenterAPI(
                self.hass,
                self.entry,
                self.entity_groups,
                self.hub_id,
                self.cntr_version,
                self.async_add_device_callback,
            )
            await self.api.start()
        except Exception as ex:
            # 생성자가 이미 세션을 열었으므로 버리기 전에 닫습니다.
            # The constructor already opened a session, so close it before dropping the API.
            await self._async_discard_api()
            raise RuntimeError(
                f"Failed to initialize Bestin hub. Host: {self.hub_id}, Version: {self.cntr_version}. "
                f"Error: {str(ex)}"
            )

    async def async_initialize_iparkapp(self) -> None:
        """iPark 스마트홈 앱 — Initialise the new gateway type.

        서버 장애/자격 증명 오류는 타입 그대로 올려보냅니다. ``__init__`` 이
        그 타입을 보고 재시도할지 사용자에게 재설정을 요구할지 결정합니다.
        실패한 API 객체는 반드시 ``stop()`` 해야 합니다 — 생성자에서 이미
        ``aiohttp.ClientSession`` 을 열었기 때문에, 그냥 버리면 재시도할 때마다
        'Unclosed client session' 이 하나씩 쌓입니다.

        Typed failures propagate unchanged so ``__init__`` can decide between
        "retry later" and "ask the user to reconfigure". The half-built API
        must still be stopped: its constructor already opened an
        ``aiohttp.ClientSession``, so dropping the reference would leak one
        session — and one "Unclosed client session" warning — per retry.
        """
        self.api = BestinIparkAppAPI(
            self.hass,
            self.entry,
            self.entity_groups,
            self.hub_id,
            self.async_add_device_callback,
        )
        try:
            await self.api.start()
        except BestinIparkAppError:
            await self._async_discard_api()
            raise
        except Exception as ex:
            await self._async_discard_api()
            raise IparkAppConnectionError(
                f"Failed to initialize Bestin iParkApp hub. Host: {self.hub_id}. "
                f"Error: {ex!s}"
            ) from ex

    async def _async_discard_api(self) -> None:
        """실패한 API 객체를 정리합니다 — Tear down a half-started API."""
        api, self.api = self.api, None
        if api is None:
            return
        try:
            await api.stop()
        except Exception as ex:  # noqa: BLE001 — cleanup must not mask the cause
            LOGGER.debug("API cleanup after failed start: %s", ex)
