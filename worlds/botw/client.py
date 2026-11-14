"""Breath of the Wild client: Archipelago <-> Savage Wind.

Checks: read from the game's own save (game_data.sav, a hash/value list of every gamedata flag) each time the game
saves. Items: given in play through Savage Wind's control console (SAVAGEWIND_CONTROL=<port>, `give <actor> <n>`).
"""
import asyncio
import glob
import json
import os
import time
import zlib

import Utils
from CommonClient import ClientCommandProcessor, CommonContext, get_base_parser, gui_enabled, logger, server_loop
from NetUtils import ClientStatus

from . import LOC_BASE
from .items import CHAMPION_POWERS, GAME, ITEMS, TRAPS
from .save import read_save

CONFIG = Utils.user_path("botw_client.json")
DEFAULT_PORT = 26763
GOAL_BOOL = zlib.crc32(b"GanonQuest_Finished")
GOAL_COUNT = zlib.crc32(b"Defeated_Enemy_GanonBeast_Num")


class SavageWind:
    """One line per command, one JSON line back: {"ok": true, "data": {...}} or {"ok": false, "error": "..."}."""

    def __init__(self):
        self.reader = self.writer = None
        self.lock = asyncio.Lock()

    async def cmd(self, line: str, port: int) -> dict:
        async with self.lock:
            try:
                if not self.writer:
                    self.reader, self.writer = await asyncio.wait_for(
                        asyncio.open_connection("127.0.0.1", port), 3)
                    logger.info(f"Connected to Savage Wind on port {port}")
                self.writer.write(line.encode() + b"\n")
                await self.writer.drain()
                reply = await asyncio.wait_for(self.reader.readline(), 10)
                if not reply:
                    raise ConnectionError("closed")
                return json.loads(reply)
            except (OSError, asyncio.TimeoutError, ConnectionError, ValueError) as e:
                if self.writer:
                    logger.info(f"Lost Savage Wind ({e!r}); retrying")
                    self.writer.close()
                self.reader = self.writer = None
                return {"ok": False, "error": "not connected", "offline": True}


class BotWCommands(ClientCommandProcessor):
    def _cmd_folder(self, path: str = "") -> bool:
        """Set the Savage Wind folder (the one with savagewind.exe and save/)."""
        if not os.path.isdir(os.path.join(path, "save")):
            self.output(f"No save folder in {path!r}")
            return False
        self.ctx.config["folder"] = path
        self.ctx.save_config()
        self.output(f"Savage Wind folder: {path}")
        return True

    def _cmd_port(self, port: str = "") -> bool:
        """Set the control console port (SAVAGEWIND_CONTROL in Savage Wind's launch options)."""
        self.ctx.config["port"] = int(port)
        self.ctx.save_config()
        self.output(f"Port: {port}")
        return True

    def _cmd_regive(self, start: str = "0") -> bool:
        """Give items again from number <start> on (after loading an older save that lost them)."""
        self.ctx.state["given"] = max(0, int(start))
        self.ctx.save_state()
        self.output(f"Items from #{start} will be given again")
        return True

    def _cmd_sw(self, *words: str) -> bool:
        """Send a raw command to Savage Wind's console (try: sw help)."""
        async def go():
            self.output(json.dumps(await self.ctx.sw.cmd(" ".join(words), self.ctx.config["port"])))
        asyncio.create_task(go())
        return True


class BotWContext(CommonContext):
    game = GAME
    items_handling = 0b111  # own items too: a check's vanilla reward stays, its AP item only comes through here
    command_processor = BotWCommands

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.config = {"folder": "", "port": DEFAULT_PORT}
        try:
            with open(CONFIG) as f:
                self.config.update(json.load(f))
        except (OSError, ValueError):
            pass
        self.sw = SavageWind()
        self.state = {"given": 0}
        self.slot_data = {}
        self.save_mtime = 0
        self.goal_sent = False
        self.flag_addrs = {}  # flag name -> address of its hash in the live gamedata
        # Options > Archipelago in the game (patched Savage Wind: runtime/control_ap.c): its settings and Connect count
        self.ap = {}
        self.connects_seen = None
        self.status = ""
        self.deaths_seen = None  # Link's death count last read; a death we caused isn't sent back
        self.killed_at = 0.0  # when a DeathLink killed Link
        self.rupees_seen = None  # RingLink: the wallet last read; our own writes aren't sent back
        self.overlay = None
        if os.name == "nt":
            from .overlay import Overlay
            self.overlay = Overlay(self.config["folder"])
            self.overlay.start()

    def on_print_json(self, args: dict):
        super().on_print_json(args)
        if not self.overlay or args.get("type") != "ItemSend" or self.slot is None:
            return
        item, to = args["item"], args["receiving"]
        sender = item.player
        if self.slot not in (to, sender):
            return
        kind = "trap" if item.flags & 0b100 else "progression" if item.flags & 0b001 else \
            "useful" if item.flags & 0b010 else "filler"
        name = (self.item_names.lookup_in_slot(item.item, to), kind)
        if to == sender:
            self.overlay.notify("Found your ", name)
        elif to == self.slot:
            self.overlay.notify("Received ", name, " from ", (self.player_names.get(sender, "?"), "player"))
        else:
            self.overlay.notify("Sent ", name, " to ", (self.player_names.get(to, "?"), "player"),
                                ("  ·  " + self.location_names.lookup_in_slot(item.location, sender), "location"))

    # ---- Options > Archipelago in the game, and the links
    async def set_status(self, text: str):
        if text != self.status:
            self.status = text
            await self.sw.cmd("apstatus " + text.replace('"', "'"), self.config["port"])  # (the console parses quotes)

    def notify(self, *segments):
        if self.overlay:
            self.overlay.notify(*segments)

    async def game_menu_tick(self):
        r = await self.sw.cmd("ap", self.config["port"])
        if not r.get("ok"):
            return  # stock Savage Wind (no Archipelago page) or the game isn't up: the Launcher's fields still work
        self.ap = r["data"]
        # (a Connect pressed before the client started counts too: the count is per game run, 0 until a press)
        if self.ap["connects"] != (self.connects_seen or 0) and self.ap["server"] and not self.server:
            self.connects_seen = self.ap["connects"]
            self.username, self.auth = self.ap["slot"], self.ap["slot"]
            self.password = self.ap["password"] or None
            await self.set_status(f"Connecting to {self.ap['server']}...")
            await self.update_tags()  # (the links' tags go with the Connect)
            await self.connect(self.ap["server"])
        connected = self.server and self.server.socket and not self.server.socket.closed and self.slot is not None
        if connected:
            await self.set_status(f"Connected as {self.player_names.get(self.slot, self.auth)}: "
                                  f"{len(self.checked_locations)} of "
                                  f"{len(self.checked_locations) + len(self.missing_locations)} checks")
            await self.update_tags()
        elif self.status.startswith("Connected"):
            await self.set_status("Disconnected")

    async def update_tags(self):
        want = {t for t, on in (("TrapLink", self.ap.get("traplink")), ("RingLink", self.ap.get("ringlink"))) if on}
        if bool(self.ap.get("deathlink")) != ("DeathLink" in self.tags):
            await self.update_death_link(bool(self.ap.get("deathlink")))
        have = self.tags & {"TrapLink", "RingLink"}
        if want != have:
            self.tags = (self.tags - {"TrapLink", "RingLink"}) | want
            await self.send_msgs([{"cmd": "ConnectUpdate", "tags": list(self.tags)}])

    async def links_tick(self):
        port = self.config["port"]
        if "DeathLink" in self.tags:
            r = await self.sw.cmd("life", port)
            deaths = r.get("data", {}).get("deaths")
            if deaths is not None:
                if self.deaths_seen is not None and deaths > self.deaths_seen:
                    if time.time() - self.killed_at > 15:  # (a DeathLink kill isn't sent back)
                        await self.send_death(f"{self.player_names.get(self.slot, 'Link')} fell in Hyrule.")
                        self.notify(("DeathLink", "trap"), ": you died, and took everyone with you")
                self.deaths_seen = deaths
        if "RingLink" in self.tags:
            r = await self.sw.cmd("rupees", port)
            now = r.get("data", {}).get("rupees")
            if now is not None:
                if self.rupees_seen is not None and now != self.rupees_seen:
                    await self.send_msgs([{"cmd": "Bounce", "tags": ["RingLink"], "data": {
                        "time": time.time(), "source": self.slot, "amount": now - self.rupees_seen}}])
                self.rupees_seen = now

    def on_deathlink(self, data: dict):
        super().on_deathlink(data)
        self.killed_at = time.time()
        asyncio.create_task(self.sw.cmd("life kill", self.config["port"]))
        self.notify(("DeathLink", "trap"), ": ", (data.get("source", "?"), "player"), " died, and so do you")

    async def ring_in(self, amount: int):
        port = self.config["port"]
        now = (await self.sw.cmd("rupees", port)).get("data", {}).get("rupees")
        if now is None:
            return
        new = max(0, min(9999, now + amount))
        await self.sw.cmd(f"rupees {new}", port)
        self.rupees_seen = new  # (our write: not sent back)
        self.notify("RingLink: ", (f"{amount:+d} rupees", "useful"))

    async def trap_out(self, name: str):
        if "TrapLink" in self.tags:
            await self.send_msgs([{"cmd": "Bounce", "tags": ["TrapLink"], "data": {
                "time": time.time(), "source": self.player_names.get(self.slot, "?"), "trap_name": name}}])

    async def trap_in(self, data: dict):
        name = data.get("trap_name", "")
        mine = name if name in TRAPS else self.random_trap()  # another game's trap: one of ours
        await self.trap(ITEMS[mine][1][0].split()[1])
        self.notify("TrapLink: ", (name, "trap"), " from ", (data.get("source", "?"), "player"))

    @staticmethod
    def random_trap():
        import random
        return random.choice(TRAPS)

    async def flag_addr(self, name: str, kind: str):
        """Address of the flag's hash inside its live gamedata object, found with the console's memory scan.
        bool objects: vtable at -0xC, value byte at -1. s32/f32 objects: vtable at -0x1C, value at -4."""
        port, h = self.config["port"], zlib.crc32(name.encode())
        cached = self.flag_addrs.get(name)
        if cached:
            r = await self.sw.cmd(f"mem read {cached:#x} 4 u32", port)
            if r.get("ok") and int(r["data"]["value.0"]) == h:
                return cached
        await self.sw.cmd("mem reset", port)
        if not (await self.sw.cmd(f"mem scan u32 {h}", port)).get("ok"):
            return None
        for _ in range(300):
            st = await self.sw.cmd("mem scan status", port)
            if st.get("data", {}).get("done") or not st.get("ok"):
                break
            await asyncio.sleep(0.2)
        found = (await self.sw.cmd("mem list 50", port)).get("data", {})
        vt_off = 0xC if kind == "bool" else 0x1C
        for k, v in found.items():
            if k.endswith(".addr"):
                a = int(v, 16)
                r = await self.sw.cmd(f"mem read {a - vt_off:#x} 8 u64", port)
                # the game's own flag objects start with a vtable in the main module (0x70_xxxx_xxxx)
                if r.get("ok") and int(r["data"]["value.0"]) >> 32 == 0x70:
                    self.flag_addrs[name] = a
                    return a
        return None

    async def write_flag(self, op: str, name: str, value: str) -> bool:
        """!set <bool flag> 0|1, !add <s32 flag> n, !addf <f32 flag> x. Applies at the next loading screen."""
        port = self.config["port"]
        a = await self.flag_addr(name, "bool" if op == "!set" else "num")
        if a is None:
            return False
        if op == "!set":  # (bit 0 of the byte is the value; the bits above are the flag's category)
            r = await self.sw.cmd(f"mem read {a - 1:#x} 1 u8", port)
            if not r.get("ok"):
                return False
            byte = (int(r["data"]["value.0"]) & ~1) | (1 if int(value) else 0)
            return (await self.sw.cmd(f"mem write {a - 1:#x} u8 {byte}", port)).get("ok", False)
        typ = "f32" if op == "!addf" else "s32"
        r = await self.sw.cmd(f"mem read {a - 4:#x} 4 {typ}", port)
        if not r.get("ok"):
            return False
        new = float(r["data"]["value.0"]) + float(value)
        new = new if typ == "f32" else int(new)
        return (await self.sw.cmd(f"mem write {a - 4:#x} {typ} {new}", port)).get("ok", False)

    def save_config(self):
        with open(CONFIG, "w") as f:
            json.dump(self.config, f)

    def seed(self):  # (a room's seed: server_seed_name in 0.6; seed_name only comes from patch files)
        return getattr(self, "server_seed_name", None) or self.seed_name

    def state_path(self):
        return Utils.user_path(f"botw_state_{self.seed()}_{self.slot}.json")

    def save_state(self):
        if self.seed():
            with open(self.state_path(), "w") as f:
                json.dump(self.state, f)

    async def server_auth(self, password_requested: bool = False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd: str, args: dict):
        if cmd == "Bounced":
            tags, data = args.get("tags", []), args.get("data", {})
            if "RingLink" in tags and "RingLink" in self.tags and data.get("source") != self.slot:
                asyncio.create_task(self.ring_in(int(data.get("amount", 0))))
            if "TrapLink" in tags and "TrapLink" in self.tags and \
                    data.get("source") != self.player_names.get(self.slot):
                asyncio.create_task(self.trap_in(data))
        if cmd == "ConnectionRefused":
            asyncio.create_task(self.set_status("Refused: " + ", ".join(args.get("errors", []))))
        if cmd == "Connected":
            self.slot_data = args.get("slot_data", {})
            self.goal_sent = False
            self.save_mtime = 0
            try:
                with open(self.state_path()) as f:
                    self.state = json.load(f)
            except (OSError, ValueError):
                self.state = {"given": 0}
            # the save profile is bound per seed, so another profile's progress is never sent
            if not self.state.get("profile"):
                self.state["profile"] = self.newest_profile()
                self.save_state()
            logger.info(f"Reading checks from {self.state['profile']}" if self.state["profile"] else
                        "No Savage Wind save found: use /folder <Savage Wind folder>, then reconnect")

    def item_name(self, item_id: int) -> str:
        return self.item_names.lookup_in_game(item_id, GAME)

    def newest_profile(self):
        saves = glob.glob(os.path.join(self.config["folder"], "save", "save_*", "*", "game_data.sav"))
        if not saves:
            return None
        return os.path.dirname(os.path.dirname(max(saves, key=os.path.getmtime)))

    def current_save(self):
        prof = self.state.get("profile")
        saves = glob.glob(os.path.join(prof, "*", "game_data.sav")) if prof else []
        return max(saves, key=os.path.getmtime) if saves else None

    async def check_save(self):
        path = self.current_save()
        if not path or os.path.getmtime(path) == self.save_mtime:
            return
        try:
            vals = read_save(path)
        except (OSError, ValueError) as e:
            logger.info(f"Can't read the save yet: {e}")
            return
        self.save_mtime = os.path.getmtime(path)
        counters = self.slot_data.get("counters", {})  # (id -> [game data name, number]: a count reaching it)

        def done(i):
            c = counters.get(str(i))
            return (vals.get(zlib.crc32(c[0].encode()), 0) >= c[1]) if c else vals.get(i - LOC_BASE)
        found = [i for i in self.missing_locations if done(i)]
        if found:
            await self.check_locations(found)
            logger.info(f"Sent {len(found)} check(s) from the save")
        await self.check_goal(vals)

    async def check_goal(self, vals):
        if self.goal_sent or not (vals.get(GOAL_BOOL) or vals.get(GOAL_COUNT, 0) > 0):
            return
        names = [self.item_name(i.item) for i in self.items_received]
        powers = sum(n in names for n in CHAMPION_POWERS)
        need = self.slot_data.get("required_champion_powers", 4)
        if powers < need or (self.slot_data.get("goal_needs_master_sword") and "Progressive Master Sword" not in names):
            logger.info(f"Ganon is down, but the goal needs {need} champion powers (you have {powers})"
                        + (" and the Master Sword" if self.slot_data.get("goal_needs_master_sword") else ""))
            return
        await self.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
        self.goal_sent = True
        logger.info("Goal complete!")

    async def give_items(self):
        port = self.config["port"]
        while self.state["given"] < len(self.items_received):
            item = self.items_received[self.state["given"]]
            name = self.item_name(item.item)
            actions = ITEMS.get(name, (None, []))[1]
            # "step" resumes a half-done item, so a retry never applies an add twice
            copy = sum(1 for i in self.items_received[:self.state["given"] + 1] if i.item == item.item)
            for action in actions[self.state.get("step", 0):]:
                if action.startswith("@"):  # "@<k> <action>": only for the k-th copy (progressive items)
                    k, _, action = action[1:].partition(" ")
                    if int(k) != copy:
                        self.state["step"] = self.state.get("step", 0) + 1
                        continue
                if action.startswith("!demo"):
                    pass  # (the in-game item scene: only the native client drives it; the give after it is the fallback)
                elif action.startswith("!trap"):
                    await self.trap(action.split()[1])
                    await self.trap_out(name)
                elif action.startswith("!"):
                    if not await self.write_flag(*action.split()):
                        return  # not in play (no gamedata yet): try again next tick
                else:
                    # "givekey <actor> <n>" needs the patched Savage Wind (key items); the rest is "<actor> <n>" for give
                    r = await self.sw.cmd(action if action.startswith("givekey ") else f"give {action}", port)
                    if not r.get("ok"):
                        err = r.get("error", "")
                        if not any(e in err for e in ("No item", "No key item", "Unknown command")):
                            return  # not in play yet: try again next tick, from this step
                        logger.warning(f"Savage Wind can't give {action} ({name}): {err}; skipped")
                self.state["step"] = self.state.get("step", 0) + 1
                self.save_state()
            self.state["step"] = 0
            self.state["given"] += 1
            self.save_state()
            logger.info(f"Received {name} from {self.player_names.get(item.player, '?')}")

    async def trap(self, kind):
        port = self.config["port"]
        if kind == "midnight":
            await self.sw.cmd("time 0", port)
        elif kind == "thunderstorm":
            prev = (await self.sw.cmd("weather", port)).get("data", {}).get("weather", "game")
            await self.sw.cmd("weather thunderstorm", port)

            async def restore():
                await asyncio.sleep(120)
                await self.sw.cmd(f"weather {prev}", port)
            asyncio.create_task(restore())

    def run_gui(self):
        from kvui import GameManager

        class BotWManager(GameManager):
            base_title = "Breath of the Wild Client"
        self.ui = BotWManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")


async def game_loop(ctx: BotWContext):
    while not ctx.exit_event.is_set():
        try:
            await ctx.game_menu_tick()
            if ctx.slot is not None and ctx.seed():
                await ctx.check_save()
                await ctx.give_items()
                await ctx.links_tick()
        except Exception:
            logger.exception("BotW client loop")
        await asyncio.sleep(2)


def launch(*args):
    async def main(argv):
        parser = get_base_parser()
        a = parser.parse_args(argv)
        ctx = BotWContext(a.connect, a.password)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        loop = asyncio.create_task(game_loop(ctx), name="BotWLoop")
        await ctx.exit_event.wait()
        await ctx.shutdown()
        loop.cancel()

    import colorama
    colorama.just_fix_windows_console()
    asyncio.run(main(list(args)))
