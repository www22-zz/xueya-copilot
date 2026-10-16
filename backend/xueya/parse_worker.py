"""Spawned ordinary parsing processes, terminated on cancellation or timeout."""
import asyncio
import multiprocessing
from .common import AppError
from .rag import parse_document


def _parse(connection, buffer, kind):
    try:
        connection.send((True, parse_document(buffer, kind)))
    except BaseException as error:
        connection.send((False, error.code if isinstance(error, AppError) else "PARSE_FAILED"))
    finally:
        connection.close()


async def parse_artifact(buffer, kind, timeout=60):
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_parse, args=(sender, buffer, kind), daemon=True)
    process.start()
    sender.close()
    try:
        async with asyncio.timeout(timeout):
            while not receiver.poll():
                if not process.is_alive():
                    raise AppError("PARSE_FAILED")
                await asyncio.sleep(.02)
            # recv uses a thread because a partially written multi-MB frame must not block HTTP.
            ok, value = await asyncio.to_thread(receiver.recv)
            if not ok:
                raise AppError(value)
            return value
    finally:
        if process.is_alive():
            process.terminate()
        await asyncio.to_thread(process.join, 2)
        if process.is_alive():
            process.kill()
            await asyncio.to_thread(process.join, 2)
        receiver.close()
        process.close()
