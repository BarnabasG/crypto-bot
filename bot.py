# bot.py
import os
import discord
from dotenv import load_dotenv
from requests import Session, get
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
    details = get_details(search_string)
    if not details:
        await message.channel.send(f"Failed to find crypto: {search_string}")
        return
    
    #colour = get_colour(str(message.author))
    colour = get_colour(details.get('symbol'))
    msg = generate_message(details, colour)
    
    await message.channel.send(embed=msg)
    
def generate_message(details, colour):

    embed=discord.Embed(
        title=f"{details.get('name')} ({details.get('symbol')})",
        color=colour
    )
    cap = add_commas(round(round_to_n(details.get('cap'),6)))
    embed.add_field(
        name="Market Cap",
        value=f"${cap}",
        inline=True
    )
    embed.add_field(
        name="Rank",
        value=details.get('rank'),
        inline=True
    )
    embed.add_field(name=chr(173), value=chr(173))
    embed.add_field(
        name="Value (USD)",
        value=f"${format(details.get('USD'), '.2f')}",#f"${add_commas(details.get('USD'))}",
        inline=True
    )
    embed.add_field(
        name="Value (GBP)",
        value=f"${format(details.get('GBP'), '.2f')}",#f"£{add_commas(details.get('GBP'))}",
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
    print(f"Generated {s} ({(r1,r2,r3)}, {to_number(name), to_number(name+s1), to_number(name+s2)}) based on {name}")
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

    url = 'https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/latest'

    headers = {
        'Accepts': 'application/json',
        'X-CMC_PRO_API_KEY': COIN_API,
    }

    session = Session()
    session.headers.update(headers)

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
    print(data)

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