# bot.py
import os
import discord
from dotenv import load_dotenv
from requests import Session, get, request
from requests.exceptions import ConnectionError, Timeout, TooManyRedirects
import json
import logging
from math import log10, floor
import random
import sqlite3
import time
import asyncio

DB_PATH = "watchlist.db"

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
COIN_API = os.getenv('COIN_API_KEY')
EXCHANGE = os.getenv('CURRENCY_API_KEY')

client = discord.Client()

@client.event
async def on_ready():
    logging.debug(f'{client.user.name} connected to Discord')

    count = 0

    while True:

        await nft_alert_runner()

        if count%24 == 0:
            await coin_alert_runner()

        count += 1
        await asyncio.sleep(300)


async def nft_alert_runner():
    await check_nft_updates()

async def coin_alert_runner():
    await check_coin_updates()

@client.event
async def on_message(message):
    if message.author == client.user or not message.content.startswith('!'):
        return

    search_string = message.content[1:].strip()
    if search_string == '':
        return
    
    if search_string.startswith('watchlist clear nft'):
        clear_watchlist(str(message.author.id), 'nft')
        await message.channel.send(f"NFT alerts cleared for <@{str(message.author.id)}>")
        return

    if search_string.startswith('watchlist clear crypto'):
        clear_watchlist(str(message.author.id), 'crypto')
        await message.channel.send(f"Cryptocurrency alerts cleared for <@{str(message.author.id)}>")
        return
    
    if search_string.startswith('watchlist'):
        coin_alerts, nft_alerts = get_user_alerts(str(message.author.id))
        if not any((coin_alerts, nft_alerts)):
            await message.channel.send(f"No alerts set up yet. Enter an nft or cryptocurrency to watch followed by a price (ETH for nfts, $ for coins) to alert at (`!watch coolpetsnft 1.5`/`!watch eth 3000`)")
        if coin_alerts:
            colour = get_colour(str(message.author)+'crypto')
            msg = generate_watchlist_message('Cryptocurrency', coin_alerts, colour)
            await message.channel.send(embed=msg)
        if nft_alerts:
            colour = get_colour(str(message.author)+'nft')
            msg = generate_watchlist_message('NFT', nft_alerts, colour)
            await message.channel.send(embed=msg)
        return
    
    if search_string.startswith('watch'):
        commands = search_string.split(' ')
        if len(commands) > 1:
            watch_string = commands[1]
            modifiers = commands[2:] if len(commands) > 2 else None
        else:
            watch_string = None
        if not watch_string or not modifiers:
            await message.channel.send(f"Enter an nft or cryptocurrency to watch followed by a price (ETH for nfts, $ for coins) to alert at (`!watch coolpetsnft 1.5`/`!watch eth 3000`)")

        crypto_details, nft_details = get_details(watch_string)
        print(crypto_details, nft_details)
        if not any((crypto_details, nft_details)):
            await message.channel.send(f"Failed to find <{watch_string}>")
            return
        if all((crypto_details, nft_details)):
            if crypto_details.get('cap') > nft_details.get('cap'):
                if float(modifiers[0]) > crypto_details.get('USD'):
                    await message.channel.send(f"Current price for {watch_string} (${crypto_details.get('USD')}) must be higher than alert price (${modifiers[0]})")
                    return
                if coin_watchlist(watch_string, modifiers, str(message.author), str(message.author.id), message.channel.id):
                    await message.channel.send(f"Added alert for {watch_string} at floor price {modifiers[0]} (requested by <@{str(message.author.id)}>) - watching for 30 days")
                    colour = get_colour(crypto_details.get('symbol', 'none'))
                    msg = generate_crypto_message(crypto_details, colour)
                    await message.channel.send(embed=msg)
            else:
                if float(modifiers[0]) > crypto_details.get('USD'):
                    await message.channel.send(f"Current price for {watch_string} (${crypto_details.get('USD')}) must be higher than alert price (${modifiers[0]})")
                    return
                if nft_watchlist(watch_string, modifiers, str(message.author), str(message.author.id), message.channel.id):
                    await message.channel.send(f"Added alert for {watch_string} at floor price {modifiers[0]} (requested by <@{str(message.author.id)}>) - watching for 30 days")
                    colour = get_colour(nft_details.get('name', 'none'))
                    msg = generate_nft_message(nft_details, colour)
                    await message.channel.send(embed=msg)

        if crypto_details:
            if float(modifiers[0]) > crypto_details.get('USD'):
                await message.channel.send(f"Current price for {watch_string} (${crypto_details.get('USD')}) must be higher than alert price (${modifiers[0]})")
                return
            if coin_watchlist(watch_string, modifiers, str(message.author), str(message.author.id), message.channel.id):
                await message.channel.send(f"Added alert for {watch_string} at price ${modifiers[0]} (requested by <@{str(message.author.id)}>) - watching for 30 days")
                colour = get_colour(crypto_details.get('symbol', 'none'))
                msg = generate_crypto_message(crypto_details, colour)
                await message.channel.send(embed=msg)
        if nft_details:
            if float(modifiers[0]) > nft_details.get('floor'):
                await message.channel.send(f"Current price for {watch_string} ({nft_details.get('floor')} ETH) must be higher than alert price ({modifiers[0]} ETH)")
                return
            if nft_watchlist(watch_string, modifiers, str(message.author), str(message.author.id), message.channel.id):
                await message.channel.send(f"Added alert for {watch_string} at floor price {modifiers[0]} (requested by <@{str(message.author.id)}>) - watching for 30 days")
                colour = get_colour(nft_details.get('name', 'none'))
                msg = generate_nft_message(nft_details, colour)
                await message.channel.send(embed=msg)
        return
    
    if search_string == ('metrics'):
        data = metrics()
        msg = generate_metrics_message(data, 0xFFD700)
        await message.channel.send(embed=msg)
        return
    
    crypto_details, nft_details = get_details(search_string)
    if not any((crypto_details, nft_details)):
        await message.channel.send(f"Failed to find <{search_string}>")
        return
    
    #colour = get_colour(str(message.author))
    if crypto_details:
        colour = get_colour(crypto_details.get('symbol', 'none'))
        msg = generate_crypto_message(crypto_details, colour)
        await message.channel.send(embed=msg)
    if nft_details:
        colour = get_colour(nft_details.get('name', 'none'))
        msg = generate_nft_message(nft_details, colour)
        await message.channel.send(embed=msg)
    
def generate_crypto_message(details, colour):

    embed=discord.Embed(
        title=f"{details.get('name','Unknown')} ({details.get('symbol','Unknown')})",
        color=colour
    )
    cap = f"${add_commas(round(round_to_n(details.get('cap'),6)))}" if details.get('cap') else 'Unknown'
    embed.add_field(
        name="Market Cap",
        value=cap,
        inline=True
    )
    embed.add_field(
        name="Rank",
        value=details.get('rank','Unknown'),
        inline=True
    )
    embed.add_field(name=chr(173), value=chr(173))
    if details.get('USD') < 0.01:
        usd = '${0:.10f}'.format(details.get('USD'))
    else:
        usd = f"${format(details.get('USD'), '.2f')}"
    if details.get('GBP') < 0.01:
        gbp = '£{0:.10f}'.format(details.get('GBP'))
    else:
        gbp = f"£{format(details.get('GBP'), '.2f')}"
    embed.add_field(
        name="Value (USD)",
        value=usd,
        inline=True
    )
    embed.add_field(
        name="Value (GBP)",
        value=gbp,
        inline=True
    ),
    embed.add_field(name=chr(173), value=chr(173)),
    volume_change_str = f"1h: {get_volume_message(details.get('percent_1h'),2,'%')}\n24h: {get_volume_message(details.get('percent_24h'),2,'%')}\n7d: {get_volume_message(details.get('percent_7d'),2,'%')}\n30d: {get_volume_message(details.get('percent_30d'),2,'%')}"
    embed.add_field(
        name="Volume change",
        value=volume_change_str,
        inline=False
    )
    return embed

def generate_nft_message(details, colour):

    if details.get('url'):
        embed=discord.Embed(
            title=f"{details.get('name')} (Collection)",
            color=colour,
            url=details.get('url')
        )
    else:
        embed=discord.Embed(
            title=f"{details.get('name')} (Collection)",
            color=colour
        )
    if details.get("img"):
        try:
            embed.set_image(url=details.get("img"))
        except Exception as e:
            logging.warning(f"Failed to add image - {e}")
    supply = round(details.get('supply')) if details.get('supply') else 'Unknown'
    embed.add_field(
        name="Supply",
        value=supply,
        inline=True
    )
    embed.add_field(
        name="Owners",
        value=details.get('owners','Unknown'),
        inline=True
    )
    embed.add_field(name=chr(173), value=chr(173))
    cap = f"{add_commas(round(round_to_n(details.get('cap'),6)))} ETH" if details.get('cap') else 'Unknown'
    cap_usd = f"${add_commas(round(round_to_n(details.get('cap_usd'),6)))}" if details.get('cap_usd') else 'Unknown'
    embed.add_field(
        name="Market Cap",
        value=f"{cap} ({cap_usd})",
        inline=True
    )
    floor = f"{add_commas(details.get('floor'))} ETH" if details.get('floor') else 'Unknown'
    floor_usd = f"${add_commas(round(round_to_n(details.get('floor_usd'),6)))}" if details.get('floor_usd') else 'Unknown'
    embed.add_field(
        name="Floor",
        value=f"{floor} ({floor_usd})",
        inline=True
    )
    return embed

def generate_metrics_message(details, colour):

    embed=discord.Embed(
        title=f"Global Metrics",
        color=colour
    )
    embed.add_field(
        name="Active Cryptocurrencies",
        value=details.get('active_crypto','Unknown'),
        inline=True
    )
    embed.add_field(
        name="Active Market Pairs",
        value=details.get('active_market_pairs','Unknown'),
        inline=True
    )
    embed.add_field(name=chr(173), value=chr(173))
    if details.get('btc_dominance'):
        m_btc = f"{round(details.get('btc_dominance'),2)}%"
        if details.get('btc_dominance_24h_change'): m_btc += f" ({get_volume_message(details.get('btc_dominance_24h_change'),3,'%')})"
    else:
        m_btc = 'Unknown'
    if details.get('eth_dominance'):
        m_eth = f"{round(details.get('eth_dominance'),2)}%"
        if details.get('eth_dominance_24h_change'): m_eth += f" ({get_volume_message(details.get('eth_dominance_24h_change'),3,'%')})"
    else:
        m_eth = 'Unknown'
    embed.add_field(
        name="BTC Dominance",
        value=m_btc,
        inline=True
    )
    embed.add_field(
        name="ETC Dominance",
        value=m_eth,
        inline=True
    )
    embed.add_field(name=chr(173), value=chr(173))
    if details.get('defi_cap'):
        m_defi = f"${add_commas(round(round_to_n(details.get('defi_cap'),6)))}"
        if details.get('defi_cap_24h_change'): m_defi += f" ({get_volume_message(details.get('defi_cap_24h_change'),3,' ETH')})"
    else:
        m_defi = 'Unknown'
    if details.get('stablecoin_cap'):
        m_stable = f"${add_commas(round(round_to_n(details.get('stablecoin_cap'),6)))}"
        if details.get('stablecoin_cap_24h_change'): m_stable += f" ({get_volume_message(details.get('stablecoin_cap_24h_change'),3,' ETH')})"
    else:
        m_stable = 'Unknown'
    embed.add_field(
        name="Defi Market Cap",
        value=m_defi,
        inline=True
    )
    embed.add_field(
        name="Stablecoin Market Cap",
        value=m_stable,
        inline=True
    )
    embed.add_field(name=chr(173), value=chr(173))
    if details.get('market_cap_usd'):
        m_usd = f"${add_commas(round(round_to_n(details.get('market_cap_usd'),6)))}"
        if details.get('market_cap_usd_24h_change'): m_usd += f" ({get_volume_message(details.get('market_cap_usd_24h_change'),3,'%')})"
    else:
        m_usd = 'Unknown'
    embed.add_field(
        name="Total Market Cap (USD)",
        value= m_usd,
        inline=True
    )
    return embed

def generate_watchlist_message(type, alerts, colour):
    embed=discord.Embed(
        title=f"Active {'NFT' if type.lower() == 'nft' else 'Cryptocurrency'} Alerts",
        color=colour
    )
    for a in alerts:
        s = f"{get_unit_from_type(a[4],type)} ({get_remaining_time(type, a[6])} hours remaining)"
        embed.add_field(
            name=a[1].upper(),
            value=s,
            inline=False
        )
    command = 'nft' if type.lower() == 'nft' else 'crypto'
    embed.set_footer(
        text=f"use `!watchlist clear {command}` to clear {command} alerts"
    )
    return embed

def get_remaining_time(type, calls):
    if type.lower() == 'nft':
        per_hour = 12
    else:
        per_hour = 0.5
    return round(calls / per_hour)

def get_volume_message(m, places, symbol=''):
    if m:
        emoji = ':small_red_triangle:' if m > 0 else ':small_red_triangle_down:'
        return f"{emoji} {round(m,places)}{symbol}"
    return 'unknown'

def get_unit_from_type(message, type):
    if type.lower() == 'nft':
        return f'{message} ETH'
    return f'${message}'

@client.event
async def on_error(event, *args, **kwargs):
    with open('err.log', 'a') as f:
        if event == 'on_message':
            f.write(f'Unhandled message: {args[0]}\n')
        else:
            raise

def get_colour(name):
    s1, s2 = "salt1", "salt2"
    r1 = get_num(name)
    r2 = get_num(name+s1)
    r3 = get_num(name+s2)

    s = '0x%02X%02X%02X' % (r1,r2,r3)
    logging.debug(f"Generated {s} based on {name}")
    return int(s, 16)

def to_number(s):
    return int.from_bytes(s.encode(), 'little')

def get_num(name):
    random.seed(to_number(name))
    return random.randint(0,255)

def add_commas(x):
    return "{:,}".format(x)

def get_details(code):

    logging.debug(f"searching for {code}")

    coin_data = get_coin_data(code)
    nft_data = get_nft_data(code)

    return coin_data, nft_data

def get_coin_price(symbol):

    price_data = get_coin_data(symbol, symbol_only=True)
    return price_data.get("USD")

def get_coin_data(code, symbol_only=False):

    url = 'https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest'

    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': COIN_API,
    }

    session = Session()
    session.headers.update(headers)

    if symbol_only:
        symbol_data = call_symbol(code, url, session)
        data = collect_data(symbol_data)
        return data

    symbol_data = call_symbol(code, url, session)
    slug_data = call_slug(code, url, session)
    symbol_cap = get_market_cap(symbol_data)
    slug_cap = get_market_cap(slug_data)
    
    if not symbol_cap and not slug_cap:
        return None
    elif not symbol_cap:
        raw_data = slug_data
    elif not slug_cap:
        raw_data = symbol_data
    else:
        raw_data = symbol_data if symbol_cap > slug_cap else slug_data

    data = collect_data(raw_data)
    return data

def get_nft_data(code):
    
    url = f'https://api.opensea.io/api/v1/collection/{code}'

    data = call_nft_slug(url)

    return data


def call_nft_slug(url):

    try:
        response = request("GET", url)
        raw_data = json.loads(response.text)
    except (ConnectionError, Timeout, TooManyRedirects) as e:
        logging.warn(e)
        return None

    if not raw_data.get('collection'):
        return None

    owners = safeget(raw_data, 'collection', 'stats', 'num_owners')
    cap = safeget(raw_data, 'collection', 'stats', 'market_cap')
    
    if not all((owners, cap)):
        return None
    if owners < 2 or cap < 10:
        return None

    data = collect_nft_data(raw_data)

    return data

def get_nft_floor(code):

    url = f'https://api.opensea.io/api/v1/collection/{code}'

    try:
        response = request("GET", url)
        raw_data = json.loads(response.text)
    except (ConnectionError, Timeout, TooManyRedirects) as e:
        logging.warn(e)
        return None

    if not raw_data.get('collection'):
        return None

    floor = safeget(raw_data, 'collection', 'stats', 'floor_price')

    return floor if floor else 0

def collect_nft_data(data):

    stats = safeget(data, 'collection', 'stats')
    eth_floor_price = stats.get("floor_price")
    eth_market_cap = stats.get("market_cap")
    eth_price = get_coin_price('ETH')
    if eth_price:
        usd_floor_price = eth_floor_price * eth_price if eth_floor_price else None
        usd_market_cap = eth_market_cap * eth_price if eth_market_cap else None
    else:
        usd_floor_price = None
        usd_market_cap = None

    data = {
        "name": safeget(data, 'collection', 'slug'),
        "img": safeget(data, 'collection', 'image_url'),
        "supply": stats.get("total_supply"),
        "owners": stats.get("num_owners"),
        "cap": eth_market_cap,
        "cap_usd": usd_market_cap,
        "floor": eth_floor_price,
        "floor_usd": usd_floor_price,
        "url": safeget(data, 'collection', 'external_url')
    }

    return data
    
def call_slug(code, url, session):

    parameters = {
        'slug':code.lower()
    }

    try:
        response = session.get(url, params=parameters)
        raw_data = json.loads(response.text)
    except (ConnectionError, Timeout, TooManyRedirects) as e:
        logging.warn(e)
        return None

    key = get_key(raw_data)
    data = fetch_from_dict_slug(raw_data, key)

    return data

def call_symbol(code, url, session):

    parameters = {
        'symbol':code.upper()
    }

    try:
        response = session.get(url, params=parameters)
        raw_data = json.loads(response.text)
    except (ConnectionError, Timeout, TooManyRedirects) as e:
        logging.warning(e)
        return None

    key = get_key(raw_data)
    data = fetch_from_dict_symbol(raw_data, key)

    return data


def get_market_cap(data):

    return safeget(data, 'quote', 'USD', 'market_cap') 

def get_key(data):

    dict = data.get('data')
    if not dict:
        return None

    return tuple(dict.keys())[0]


def fetch_from_dict_symbol(data, key):
    return safeget(data, 'data', key, 0)

def fetch_from_dict_slug(data, key):
    return safeget(data, 'data', key)

def get_fx_rate():
    url = f"https://free.currconv.com/api/v7/convert?q=USD_GBP&compact=ultra&apiKey={EXCHANGE}"
    response = get(url)
    return response.json().get('USD_GBP',0)

def collect_data(data):

    quote = safeget(data, 'quote', 'USD')

    if quote:
        usd = quote.get('price')
        fx_rate_usd_gbp = get_fx_rate()
        gbp = fx_rate_usd_gbp * usd
    
    data = {
        "name": data.get('name'),
        "symbol": data.get('symbol'),
        "cap": get_market_cap(data),
        "rank": data.get('cmc_rank'),
        "fiat": True if data.get('is_fiat') == 1 else False,
        "USD": usd,
        "GBP": gbp,
        "percent_1h": quote.get('percent_change_1h'),
        "percent_24h": quote.get('percent_change_24h'),
        "percent_7d": quote.get('percent_change_7d'),
        "percent_30d": quote.get('percent_change_30d')
    }

    return data


def round_to_n(x, n):
    return round(x, -int(floor(log10(abs(x))))+(n-1))

def metrics():
    
    url = 'https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest'

    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': COIN_API,
    }

    session = Session()
    session.headers.update(headers)

    try:
        response = session.get(url)
        raw_data = json.loads(response.text)
    except (ConnectionError, Timeout, TooManyRedirects) as e:
        logging.warning(e)
        return None
    
    data = collect_metric_data(raw_data)

    return data
    

def collect_metric_data(raw_data):

    data = {
        "active_crypto": safeget(raw_data, 'data', 'active_cryptocurrencies'),
        "active_market_pairs": safeget(raw_data, 'data', 'active_market_pairs'),
        "btc_dominance": safeget(raw_data, 'data', 'btc_dominance'),
        "eth_dominance": safeget(raw_data, 'data', 'eth_dominance'),
        "btc_dominance_24h_change": safeget(raw_data, 'data', 'btc_dominance_24h_percentage_change'),
        "eth_dominance_24h_change": safeget(raw_data, 'data', 'eth_dominance_24h_percentage_change'),
        "defi_cap": safeget(raw_data, 'data', 'defi_market_cap'),
        "defi_cap_24h_change": safeget(raw_data, 'data', 'defi_24h_percentage_change'),
        "stablecoin_cap": safeget(raw_data, 'data', 'stablecoin_market_cap'),
        "stablecoin_cap_24h_change": safeget(raw_data, 'data', 'stablecoin_24h_percentage_change'),
        "market_cap_usd": safeget(raw_data, 'data', 'quote', 'USD', 'total_market_cap'),
        "market_cap_usd_24h_change": safeget(raw_data, 'data', 'quote', 'USD', 'total_market_cap_yesterday_percentage_change')
    }

    return data

def nft_watchlist(item, modifiers, requester, requester_id, channel_id):
    _, nft_jobs = get_user_alerts(requester_id)
    nft_jobs = [(n[1], float(n[4])) for n in nft_jobs]
    if (item, float(modifiers[0])) in nft_jobs:
        logging.warning(f"{time.ctime()}: Did not create alert for {item} at {modifiers[0]} ETH for {requester} ({requester_id}) as this alert already exists")
        return False
    add_to_nft_watchlist(item, modifiers[0], requester, requester_id, channel_id)
    return True

def add_to_nft_watchlist(item, alert_floor, requester, requester_id, channel_id):
    
    default_watch_duration = 12 * 24 * 30 # 1 month of every 5 minutes

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO nft_watchlist "
            "(name, requester, requester_id, alert_value, triggered, watch_limit, time_added, active, channel_id)"
            "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)",
            (item, requester, requester_id, alert_floor, 0, default_watch_duration, 'Y', channel_id)
        )
        conn.commit()

    print(f"Added alert for {item} at floor price {alert_floor} (requested by <@{requester_id}>) - watching for {default_watch_duration} seconds")

async def check_nft_updates():
    logging.warning(f"{time.ctime()}: Updating NFT alerts")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT * "
        "FROM nft_watchlist "
        "WHERE active=?;",
        ('Y',)
    )
    jobs = cur.fetchall()
    await nft_alert(jobs)

async def nft_alert(alert_data):

    found = {}
    for alert in alert_data:
        slug = alert[1]
        #data = get_nft_data(slug)
        #price = data.get('floor')
        if found.get(slug):
            price = found.get(slug)
        else:
            price = get_nft_floor(slug)
            found[slug] = price
        channel_id = alert[9]
        requester_id = alert[3]
        if price > alert[4]:
            continue
        await send_nft_alert(channel_id, requester_id, alert[1], price, alert[4], str(alert[0]))
    
    for alert in alert_data:
        decrement_watch_limit(str(alert[0]), 'nft')

def decrement_watch_limit(alert_id, type):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        if type == 'nft':
            cur.execute(
                "UPDATE nft_watchlist "
                "SET watch_limit=watch_limit-1 "
                "WHERE alert_id=?",
                (alert_id,)
            )
            conn.commit()
            cur.execute(
                "SELECT watch_limit "
                "FROM nft_watchlist "
                "WHERE alert_id=?",
                (alert_id,)
            )
            res = cur.fetchone()[0]
            if res <= 0:
                cur.execute(
                    "UPDATE nft_watchlist "
                    "SET active='N' "
                    "WHERE alert_id=?",
                    (alert_id,)
                )
                conn.commit()
        else:
            cur.execute(
                "UPDATE coin_watchlist "
                "SET watch_limit=watch_limit-1 "
                "WHERE alert_id=?",
                (alert_id,)
            )
            conn.commit()
            cur.execute(
                "SELECT watch_limit "
                "FROM coin_watchlist "
                "WHERE alert_id=?",
                (alert_id,)
            )
            res = cur.fetchone()[0]
            if res <= 0:
                cur.execute(
                    "UPDATE coin_watchlist "
                    "SET active='N' "
                    "WHERE alert_id=?",
                    (alert_id,)
                )
                conn.commit()

async def send_nft_alert(channel_id, requester_id, item, value, alert_value, alert_id):
    try:
        channel = client.get_channel(channel_id)
        await channel.send(f"Heads up <@{requester_id}>, {item} just hit {value} ETH floor (you set up an alert for {alert_value} ETH)")
        update_after_alert(alert_id, 'nft')
    except Exception as e:
        print(f"Failed to send message to channel {channel} ({channel_id})")
        print(e)


def update_after_alert(alert_id, type):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        if type == 'nft':
            cur.execute(
                "UPDATE nft_watchlist "
                "SET triggered=triggered+1, active=?"
                "WHERE alert_id=?",
                ('N', alert_id)
            )
            conn.commit()
        else:
            cur.execute(
                "UPDATE coin_watchlist "
                "SET triggered=triggered+1, active=?"
                "WHERE alert_id=?",
                ('N', alert_id)
            )
            conn.commit()


def coin_watchlist(item, modifiers, requester, requester_id, channel_id):
    coin_jobs, _ = get_user_alerts(requester_id)
    coin_jobs = [(c[1], float(c[4])) for c in coin_jobs]
    if (item, float(modifiers[0])) in coin_jobs:
        logging.warning(f"{time.ctime()}: Did not create alert for {item} at ${modifiers[0]} for {requester} ({requester_id}) as this alert already exists")
        return False
    add_to_coin_watchlist(item, modifiers[0], requester, requester_id, channel_id)
    return True

def add_to_coin_watchlist(item, alert_floor, requester, requester_id, channel_id):
    
    #search_interval = interval * 60 # 30 minutes
    default_watch_duration = 0.5 * 24 * 30 # 1 month of every 5 minutes

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO coin_watchlist "
            "(name, requester, requester_id, alert_value, triggered, watch_limit, time_added, active, channel_id)"
            "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)",
            (item, requester, requester_id, alert_floor, 0, default_watch_duration, 'Y', channel_id)
        )
        conn.commit()

    print(f"Added alert for {item} at floor price {alert_floor} (requested by <@{requester_id}>) - watching for {default_watch_duration} seconds")

async def check_coin_updates():
    logging.warning(f"{time.ctime()}: Updating cryptocurrency alerts")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT * "
        "FROM coin_watchlist "
        "WHERE active=?;",
        ('Y',)
    )
    jobs = cur.fetchall()
    await coin_alert(jobs)

async def coin_alert(alert_data):

    found = {}
    for alert in alert_data:
        symbol = alert[1]
        if found.get(symbol):
            price = found.get(symbol)
        else:
            data = get_coin_data(symbol, symbol_only=True)
            price = data.get('USD')
            found[symbol] = price
        channel_id = alert[9]
        requester_id = alert[3]
        if price > alert[4]:
            continue
        await send_coin_alert(channel_id, requester_id, alert[1], price, alert[4], str(alert[0]))
    
    for alert in alert_data:
        decrement_watch_limit(str(alert[0]), 'coin')

async def send_coin_alert(channel_id, requester_id, item, value, alert_value, alert_id):
    try:
        channel = client.get_channel(channel_id)
        await channel.send(f"Heads up <@{requester_id}>, {item} just hit ${value} (you set up an alert for ${alert_value})")
        update_after_alert(alert_id, 'coin')
    except Exception as e:
        print(f"Failed to send message to channel {channel} ({channel_id})")
        print(e)

def get_user_alerts(requester_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * "
            "FROM nft_watchlist "
            "WHERE requester_id=? "
            "AND active='Y';",
            (requester_id,)
        )
        nft_jobs = cur.fetchall()
        cur.execute(
            "SELECT * "
            "FROM coin_watchlist "
            "WHERE requester_id=? "
            "AND active='Y';",
            (requester_id,)
        )
        coin_jobs = cur.fetchall()
        return coin_jobs, nft_jobs

def clear_watchlist(requester_id, type):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        if type.lower() == 'nft':
            cur.execute(
                "UPDATE nft_watchlist "
                "SET active='N' "
                "WHERE requester_id=? "
                "AND active='Y';",
                (requester_id,)
            )
        else:
            cur.execute(
                "UPDATE coin_watchlist "
                "SET active='N' "
                "WHERE requester_id=? "
                "AND active='Y';",
                (requester_id,)
            )
        conn.commit()


def safeget(dct: dict, *keys):
    """
    Safely gets key from possibly nested dictionary with error trapping and
    logging failures.
    """
    for key in keys:
        try:
            dct = dct[key]
        except KeyError:
            logging.debug(f"Safeget failed to find key '{key}' in dict")
            return None
        except Exception as e:
            logging.debug(f"Error in dictionary key search - {e} = {key}")
            return None
    return dct

if __name__ == "__main__":
    client.run(TOKEN)
