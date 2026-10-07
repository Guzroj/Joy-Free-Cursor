import asyncio, struct
from bleak import BleakClient

DIRECCION = "00:70:07:e7:98:56"
UUID_SENS = "8f3c0004-5b7a-4e2d-9c1a-0d4f6a2b7e10"

async def main():
    async with BleakClient(DIRECCION) as c:
        v = struct.unpack("<H", await c.read_gatt_char(UUID_SENS))[0]
        print("Sensibilidad actual:", v, "%")
        await c.write_gatt_char(UUID_SENS, struct.pack("<H", 200), response=True)
        v = struct.unpack("<H", await c.read_gatt_char(UUID_SENS))[0]
        print("Sensibilidad nueva:", v, "%")

asyncio.run(main())