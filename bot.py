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

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
COIN_API = os.getenv('COIN_API_KEY')
EXCHANGE = os.getenv('CURRENCY_API_KEY')

client = discord.Client()

@client.event
async def on_ready():
    logging.debug(f'{client.user.name} connected to Discord')

@client.event
async def on_message(message):
    if message.author == client.user or not message.content.startswith('!'):
        return
    
    if str(message.author) == 'benny33#4444':
        await message.channel.send(f"Ben noob")

    search_string = message.content[1:].strip()
    if search_string.strip() == '':
        return
    crypto_details, nft_details = get_details(search_string)
    print(crypto_details, nft_details)
    if not any((crypto_details, nft_details)):
        await message.channel.send(f"Failed to find {search_string}")
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
    )
    return embed

def generate_nft_message(details, colour):

    embed=discord.Embed(
        title=f"{details.get('name')} (Collection)",
        color=colour
    )
    if details.get("img"):
        embed.set_image(url=details.get("img"))
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
    cap = f"${add_commas(round(round_to_n(details.get('cap'),6)))}" if details.get('cap') else 'Unknown'
    embed.add_field(
        name="Market Cap",
        value=cap,
        inline=True
    )
    floor = f"{add_commas(details.get('floor'))}" if details.get('floor') else 'Unknown'
    if details.get('floor_usd'):
        if details.get('floor_usd') < 0.01:
            floor_usd = '${0:.10f}'.format(details.get('floor_usd'))
        else:
            floor_usd = f"${format(details.get('floor_usd'), '.2f')}"
    else:
        floor_usd = 'Unknown'
    embed.add_field(
        name="Floor",
        value=f"{floor} ({floor_usd})",
        inline=True
    )
    return embed


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

def get_eth_price():

    price_data = get_coin_data('ETH', symbol_only=True)
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

    data = collect_nft_data(raw_data)

    if not data.get('owners') or not data.get('cap'):
        return None
    if data.get('owners') < 2 or data.get('cap') < 10:
        return None

    return data

def collect_nft_data(data):

    stats = safeget(data, 'collection', 'stats')

    eth_floor_price = stats.get("floor_price")
    eth_price = get_eth_price()
    if eth_price:
        usd_floor_price = eth_floor_price * eth_price
    else:
        usd_floor_price = None

    data = {
        "name": safeget(data, 'collection', 'slug'),
        "img": safeget(data, 'collection', 'image_url'),
        "supply": stats.get("total_supply"),
        "owners": stats.get("num_owners"),
        "cap": stats.get("market_cap"),
        "floor": eth_floor_price,
        "floor_usd": usd_floor_price
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

    usd = safeget(data, 'quote', 'USD', 'price')
    fx_rate_usd_gbp = get_fx_rate()
    gbp = fx_rate_usd_gbp * usd
    
    data = {
        "name": data.get('name'),
        "symbol": data.get('symbol'),
        "cap": get_market_cap(data),
        "rank": data.get('cmc_rank'),
        "fiat": True if data.get('is_fiat') == 1 else False,
        "USD": usd,
        "GBP": gbp #float(format(gbp, ".2f"))
    }

    return data


def round_to_n(x, n):
    return round(x, -int(floor(log10(abs(x))))+(n-1))

def metrics():
    pass

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


client.run(TOKEN)
