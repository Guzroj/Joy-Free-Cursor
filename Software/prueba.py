import asyncio, struct
from bleak import BleakClient

DIRECCION = "00:70:07:e7:98:56"
UUID_ANGULO = "8f3c0002-5b7a-4e2d-9c1a-0d4f6a2b7e10"

def al_recibir(_, datos):
    centi = struct.unpack("<h", datos)[0]
    print(f"Ángulo del cuello: {centi / 100:7.2f}°")

async def main():
    async with BleakClient(DIRECCION, timeout=20) as cliente:
        print("Conectado")
        await cliente.start_notify(UUID_ANGULO, al_recibir)
        await asyncio.sleep(30)

asyncio.run(main())