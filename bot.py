"""
한국어 디스코드 경제 봇 (로블록스 연동 제거 버전)

계좌 관리, 송금, 관리자 기능을 포함한 가상 경제 시스템
"""

import os
import json
import asyncio
import random
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands
import pandas as pd

load_dotenv()
TOKEN = os.environ.get("DISCORD_TOKEN")

# 파일 경로 상수
DATA_FILE = "users.json"
SETTINGS_FILE = "admin_settings.json"
PUBLIC_ACCOUNTS_FILE = "public_accounts.json"
TRANSACTIONS_FILE = "transactions.json"
ACCOUNT_MAPPING_FILE = "account_mapping.json"

ADMIN_USER_IDS = [496921375768838154, 559307598848065537]

# 파일 생성 함수
def ensure_file(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=4)

ensure_file(DATA_FILE, {})
ensure_file(SETTINGS_FILE, {
    "transaction_fee": {"enabled": False, "min_amount": 0, "fee_rate": 0.0},
    "tax_system": {"enabled": False, "rate": 0.0, "period_days": 30, "last_collected": None, "tax_name": "세금"},
    "salary_system": {"enabled": False, "salaries": {}, "last_paid": None, "source_account": {}},
    "frozen_accounts": {}
})
ensure_file(PUBLIC_ACCOUNTS_FILE, {})
ensure_file(TRANSACTIONS_FILE, [])

# 파일 로드/저장 함수
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_users(): return load_json(DATA_FILE)
def save_users(data): save_json(DATA_FILE, data)
def load_settings(): return load_json(SETTINGS_FILE)
def save_settings(data): save_json(SETTINGS_FILE, data)
def load_public_accounts(): return load_json(PUBLIC_ACCOUNTS_FILE)
def save_public_accounts(data): save_json(PUBLIC_ACCOUNTS_FILE, data)
def load_transactions(): return load_json(TRANSACTIONS_FILE)
def save_transactions(data): save_json(TRANSACTIONS_FILE, data)

def load_account_mapping():
    if not os.path.exists(ACCOUNT_MAPPING_FILE):
        return {}
    try:
        return load_json(ACCOUNT_MAPPING_FILE)
    except:
        return {}

def save_account_mapping(mapping):
    save_json(ACCOUNT_MAPPING_FILE, mapping)

# 숫자 포맷
def format_number_4digit(num: int) -> str:
    return f"{num:,}"

# 계좌번호 생성
def generate_account_number():
    users = load_users()
    account_mapping = load_account_mapping()
    public_accounts = load_public_accounts()
    existing_numbers = set()
    for account_data in users.values():
        if '계좌번호' in account_data:
            existing_numbers.add(account_data['계좌번호'])
    existing_numbers.update(account_mapping.keys())
    for public_account_data in public_accounts.values():
        existing_numbers.add(public_account_data["account_number"])
    while True:
        account_number = f"{random.randint(1000, 9999)}"
        if account_number not in existing_numbers:
            return account_number

def get_account_number_by_user(user_id):
    mapping = load_account_mapping()
    for account_num, data in mapping.items():
        if data.get('user_id') == user_id:
            return account_num
    return None

def verify_public_account(account_number, password):
    public_accounts = load_public_accounts()
    for account_name, account_data in public_accounts.items():
        if account_data["account_number"] == account_number and account_data["password"] == password:
            return account_name
    return None

def calculate_transaction_fee(amount: int) -> int:
    fee_config = load_settings()["transaction_fee"]
    if not fee_config["enabled"] or amount < fee_config["min_amount"]:
        return 0
    return int(amount * fee_config["fee_rate"])

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS

def is_account_frozen(account_identifier: str) -> bool:
    return account_identifier in load_settings().get("frozen_accounts", {})

def set_account_frozen(account_identifier: str, frozen: bool, reason: str = ""):
    settings = load_settings()
    frozen_accounts = settings.setdefault("frozen_accounts", {})
    if frozen:
        frozen_accounts[account_identifier] = {
            "frozen_at": datetime.now().isoformat(),
            "reason": reason
        }
    else:
        frozen_accounts.pop(account_identifier, None)
    save_settings(settings)

def add_transaction(transaction_type: str, from_user: str, to_user: str, amount: int, fee: int = 0, memo: str = ""):
    transactions = load_transactions()
    transactions.append({
        "timestamp": datetime.now().isoformat(),
        "type": transaction_type,
        "from_user": from_user,
        "to_user": to_user,
        "amount": amount,
        "fee": fee,
        "memo": memo
    })
    if len(transactions) > 1000:
        transactions = transactions[-1000:]
    save_transactions(transactions)

# 봇 인텐트 및 생성
intents = discord.Intents.default()
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 봇 이벤트
@bot.event
async def on_ready():
    print(f'{bot.user} 봇이 준비되었습니다!')
    try:
        synced = await bot.tree.sync()
        print(f'{len(synced)}개의 슬래시 명령어가 동기화되었습니다.')
    except Exception as e:
        print(f'명령어 동기화 실패: {e}')

# 슬래시 명령어들
@bot.tree.command(name="계좌생성", description="새로운 계좌를 생성합니다")
async def create_account(interaction: discord.Interaction):
    user_id = interaction.user.id
    
    # 이미 계좌가 있는지 확인
    existing_account = get_account_number_by_user(user_id)
    if existing_account:
        await interaction.response.send_message("⚠️ 이미 계좌가 존재합니다. `/잔액` 명령어로 확인하세요.", ephemeral=True)
        return
    
    # 새 계좌 생성
    account_number = generate_account_number()
    users = load_users()
    
    # 사용자 데이터 생성
    users[account_number] = {
        "이름": interaction.user.display_name,
        "계좌번호": account_number,
        "잔액": 1000000  # 초기 지급금 100만원
    }
    save_users(users)
    
    # 계좌 매핑 저장
    mapping = load_account_mapping()
    mapping[account_number] = {
        "user_id": user_id,
        "discord_name": interaction.user.display_name,
        "created_at": datetime.now().isoformat()
    }
    save_account_mapping(mapping)
    
    # 거래 내역 추가
    add_transaction("계좌생성", "SYSTEM", account_number, 1000000, 0, "신규 계좌 생성")
    
    embed = discord.Embed(title="🎉 계좌 생성 완료!", color=0x00ff00)
    embed.add_field(name="계좌번호", value=f"`{account_number}`", inline=False)
    embed.add_field(name="예금주", value=interaction.user.display_name, inline=False)
    embed.add_field(name="초기 잔액", value="1,000,000원", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="잔액", description="자신의 계좌 정보를 확인합니다")
async def check_balance(interaction: discord.Interaction):
    account_number = get_account_number_by_user(interaction.user.id)
    if not account_number:
        await interaction.response.send_message("❌ 계좌가 없습니다. `/계좌생성` 명령어로 먼저 계좌를 만드세요.", ephemeral=True)
        return
    
    users = load_users()
    user_data = users[account_number]
    
    embed = discord.Embed(title="💰 계좌 정보", color=0x0099ff)
    embed.add_field(name="계좌번호", value=f"`{account_number}`", inline=False)
    embed.add_field(name="예금주", value=user_data["이름"], inline=False)
    embed.add_field(name="현재 잔액", value=f"{format_number_4digit(user_data['잔액'])}원", inline=False)
    
    # 계좌 상태 표시
    if is_account_frozen(account_number):
        embed.add_field(name="계좌 상태", value="🔒 동결됨", inline=False)
        embed.color = 0xff0000
    else:
        embed.add_field(name="계좌 상태", value="✅ 정상", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="정보", description="다른 사용자의 계좌 정보를 조회합니다")
async def user_info(interaction: discord.Interaction, 멤버: discord.Member):
    account_number = get_account_number_by_user(멤버.id)
    if not account_number:
        await interaction.response.send_message("❌ 해당 사용자는 계좌가 없습니다.", ephemeral=True)
        return
    
    users = load_users()
    user_data = users[account_number]
    
    embed = discord.Embed(title="👤 사용자 정보", color=0x0099ff)
    embed.add_field(name="계좌번호", value=f"`{account_number}`", inline=False)
    embed.add_field(name="예금주", value=user_data["이름"], inline=False)
    embed.add_field(name="현재 잔액", value=f"{format_number_4digit(user_data['잔액'])}원", inline=False)
    
    # 계좌 상태 표시
    if is_account_frozen(account_number):
        embed.add_field(name="계좌 상태", value="🔒 동결됨", inline=False)
        embed.color = 0xff0000
    else:
        embed.add_field(name="계좌 상태", value="✅ 정상", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="송금", description="다른 사용자에게 돈을 송금합니다")
async def transfer_money(interaction: discord.Interaction, 받는사람: discord.Member, 금액: int, 메모: str = ""):
    sender_account = get_account_number_by_user(interaction.user.id)
    if not sender_account:
        await interaction.response.send_message("❌ 계좌가 없습니다. `/계좌생성` 명령어로 먼저 계좌를 만드세요.", ephemeral=True)
        return
    
    recipient_account = get_account_number_by_user(받는사람.id)
    if not recipient_account:
        await interaction.response.send_message("❌ 받는 사람이 계좌가 없습니다.", ephemeral=True)
        return
    
    if sender_account == recipient_account:
        await interaction.response.send_message("❌ 자신에게는 송금할 수 없습니다.", ephemeral=True)
        return
    
    if 금액 <= 0:
        await interaction.response.send_message("❌ 송금 금액은 0보다 커야 합니다.", ephemeral=True)
        return
    
    # 계좌 동결 확인
    if is_account_frozen(sender_account):
        await interaction.response.send_message("❌ 송금자의 계좌가 동결되어 송금할 수 없습니다.", ephemeral=True)
        return
    
    if is_account_frozen(recipient_account):
        await interaction.response.send_message("❌ 수취인의 계좌가 동결되어 송금할 수 없습니다.", ephemeral=True)
        return
    
    users = load_users()
    sender_data = users[sender_account]
    recipient_data = users[recipient_account]
    
    # 수수료 계산
    fee = calculate_transaction_fee(금액)
    total_amount = 금액 + fee
    
    # 잔액 확인
    if sender_data["잔액"] < total_amount:
        await interaction.response.send_message(
            f"❌ 잔액이 부족합니다.\n현재 잔액: {format_number_4digit(sender_data['잔액'])}원\n필요 금액: {format_number_4digit(total_amount)}원 (송금액: {format_number_4digit(금액)}원 + 수수료: {format_number_4digit(fee)}원)", 
            ephemeral=True
        )
        return
    
    # 송금 실행
    sender_data["잔액"] -= total_amount
    recipient_data["잔액"] += 금액
    save_users(users)
    
    # 거래 내역 추가
    add_transaction("송금", sender_account, recipient_account, 금액, fee, 메모)
    
    embed = discord.Embed(title="💸 송금 완료", color=0x00ff00)
    embed.add_field(name="송금자", value=f"{interaction.user.display_name} (`{sender_account}`)", inline=False)
    embed.add_field(name="수취인", value=f"{받는사람.display_name} (`{recipient_account}`)", inline=False)
    embed.add_field(name="송금액", value=f"{format_number_4digit(금액)}원", inline=True)
    embed.add_field(name="수수료", value=f"{format_number_4digit(fee)}원", inline=True)
    embed.add_field(name="총 차감액", value=f"{format_number_4digit(total_amount)}원", inline=True)
    embed.add_field(name="송금자 잔액", value=f"{format_number_4digit(sender_data['잔액'])}원", inline=True)
    embed.add_field(name="수취인 잔액", value=f"{format_number_4digit(recipient_data['잔액'])}원", inline=True)
    if 메모:
        embed.add_field(name="메모", value=메모, inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="계좌송금", description="계좌번호로 직접 송금합니다")
async def transfer_by_account(interaction: discord.Interaction, 계좌번호: str, 금액: int, 메모: str = ""):
    sender_account = get_account_number_by_user(interaction.user.id)
    if not sender_account:
        await interaction.response.send_message("❌ 계좌가 없습니다. `/계좌생성` 명령어로 먼저 계좌를 만드세요.", ephemeral=True)
        return
    
    users = load_users()
    if 계좌번호 not in users:
        await interaction.response.send_message("❌ 존재하지 않는 계좌번호입니다.", ephemeral=True)
        return
    
    if sender_account == 계좌번호:
        await interaction.response.send_message("❌ 자신에게는 송금할 수 없습니다.", ephemeral=True)
        return
    
    if 금액 <= 0:
        await interaction.response.send_message("❌ 송금 금액은 0보다 커야 합니다.", ephemeral=True)
        return
    
    # 계좌 동결 확인
    if is_account_frozen(sender_account):
        await interaction.response.send_message("❌ 송금자의 계좌가 동결되어 송금할 수 없습니다.", ephemeral=True)
        return
    
    if is_account_frozen(계좌번호):
        await interaction.response.send_message("❌ 수취인의 계좌가 동결되어 송금할 수 없습니다.", ephemeral=True)
        return
    
    sender_data = users[sender_account]
    recipient_data = users[계좌번호]
    
    # 수수료 계산
    fee = calculate_transaction_fee(금액)
    total_amount = 금액 + fee
    
    # 잔액 확인
    if sender_data["잔액"] < total_amount:
        await interaction.response.send_message(
            f"❌ 잔액이 부족합니다.\n현재 잔액: {format_number_4digit(sender_data['잔액'])}원\n필요 금액: {format_number_4digit(total_amount)}원 (송금액: {format_number_4digit(금액)}원 + 수수료: {format_number_4digit(fee)}원)", 
            ephemeral=True
        )
        return
    
    # 송금 실행
    sender_data["잔액"] -= total_amount
    recipient_data["잔액"] += 금액
    save_users(users)
    
    # 거래 내역 추가
    add_transaction("송금", sender_account, 계좌번호, 금액, fee, 메모)
    
    embed = discord.Embed(title="💸 송금 완료", color=0x00ff00)
    embed.add_field(name="송금자", value=f"{interaction.user.display_name} (`{sender_account}`)", inline=False)
    embed.add_field(name="수취인", value=f"{recipient_data['이름']} (`{계좌번호}`)", inline=False)
    embed.add_field(name="송금액", value=f"{format_number_4digit(금액)}원", inline=True)
    embed.add_field(name="수수료", value=f"{format_number_4digit(fee)}원", inline=True)
    embed.add_field(name="총 차감액", value=f"{format_number_4digit(total_amount)}원", inline=True)
    embed.add_field(name="송금자 잔액", value=f"{format_number_4digit(sender_data['잔액'])}원", inline=True)
    embed.add_field(name="수취인 잔액", value=f"{format_number_4digit(recipient_data['잔액'])}원", inline=True)
    if 메모:
        embed.add_field(name="메모", value=메모, inline=False)
    
    await interaction.response.send_message(embed=embed)

# 관리자 명령어들
@bot.tree.command(name="계좌동결", description="[관리자] 계좌를 동결합니다")
async def freeze_account(interaction: discord.Interaction, 계좌번호: str, 사유: str = ""):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return
    
    users = load_users()
    if 계좌번호 not in users:
        await interaction.response.send_message("❌ 존재하지 않는 계좌번호입니다.", ephemeral=True)
        return
    
    if is_account_frozen(계좌번호):
        await interaction.response.send_message("❌ 이미 동결된 계좌입니다.", ephemeral=True)
        return
    
    set_account_frozen(계좌번호, True, 사유)
    
    embed = discord.Embed(title="🔒 계좌 동결 완료", color=0xff0000)
    embed.add_field(name="계좌번호", value=f"`{계좌번호}`", inline=False)
    embed.add_field(name="예금주", value=users[계좌번호]["이름"], inline=False)
    if 사유:
        embed.add_field(name="동결 사유", value=사유, inline=False)
    embed.add_field(name="동결 시간", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="계좌해제", description="[관리자] 계좌 동결을 해제합니다")
async def unfreeze_account(interaction: discord.Interaction, 계좌번호: str):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return
    
    users = load_users()
    if 계좌번호 not in users:
        await interaction.response.send_message("❌ 존재하지 않는 계좌번호입니다.", ephemeral=True)
        return
    
    if not is_account_frozen(계좌번호):
        await interaction.response.send_message("❌ 동결되지 않은 계좌입니다.", ephemeral=True)
        return
    
    set_account_frozen(계좌번호, False)
    
    embed = discord.Embed(title="🔓 계좌 동결 해제 완료", color=0x00ff00)
    embed.add_field(name="계좌번호", value=f"`{계좌번호}`", inline=False)
    embed.add_field(name="예금주", value=users[계좌번호]["이름"], inline=False)
    embed.add_field(name="해제 시간", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="잔액수정", description="[관리자] 사용자의 잔액을 수정합니다")
async def modify_balance(interaction: discord.Interaction, 계좌번호: str, 금액: int, 사유: str = ""):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return
    
    users = load_users()
    if 계좌번호 not in users:
        await interaction.response.send_message("❌ 존재하지 않는 계좌번호입니다.", ephemeral=True)
        return
    
    old_balance = users[계좌번호]["잔액"]
    users[계좌번호]["잔액"] = 금액
    save_users(users)
    
    # 거래 내역 추가
    add_transaction("관리자수정", "ADMIN", 계좌번호, 금액 - old_balance, 0, 사유)
    
    embed = discord.Embed(title="⚙️ 잔액 수정 완료", color=0xffa500)
    embed.add_field(name="계좌번호", value=f"`{계좌번호}`", inline=False)
    embed.add_field(name="예금주", value=users[계좌번호]["이름"], inline=False)
    embed.add_field(name="이전 잔액", value=f"{format_number_4digit(old_balance)}원", inline=True)
    embed.add_field(name="수정 후 잔액", value=f"{format_number_4digit(금액)}원", inline=True)
    embed.add_field(name="변경량", value=f"{format_number_4digit(금액 - old_balance):+}원", inline=True)
    if 사유:
        embed.add_field(name="수정 사유", value=사유, inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="계좌목록", description="[관리자] 모든 계좌 목록을 확인합니다")
async def list_accounts(interaction: discord.Interaction):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return
    
    users = load_users()
    if not users:
        await interaction.response.send_message("❌ 등록된 계좌가 없습니다.", ephemeral=True)
        return
    
    embed = discord.Embed(title="📋 계좌 목록", color=0x0099ff)
    
    account_list = ""
    for account_number, data in users.items():
        status = "🔒" if is_account_frozen(account_number) else "✅"
        account_list += f"{status} `{account_number}` - {data['이름']} ({format_number_4digit(data['잔액'])}원)\n"
    
    # 메시지가 너무 길면 분할
    if len(account_list) > 1024:
        account_list = account_list[:1000] + "...\n(목록이 잘렸습니다)"
    
    embed.add_field(name="계좌 정보", value=account_list, inline=False)
    embed.add_field(name="총 계좌 수", value=f"{len(users)}개", inline=True)
    
    total_balance = sum(data["잔액"] for data in users.values())
    embed.add_field(name="총 자산", value=f"{format_number_4digit(total_balance)}원", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# 공용 계좌 관련 명령어들
@bot.tree.command(name="공용계좌생성", description="[관리자] 새로운 공용 계좌를 생성합니다")
async def create_public_account(interaction: discord.Interaction, 계좌이름: str, 패스워드: str, 초기잔액: int = 0):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return
    
    public_accounts = load_public_accounts()
    
    # 이미 존재하는 계좌명인지 확인
    if 계좌이름 in public_accounts:
        await interaction.response.send_message("❌ 이미 존재하는 공용 계좌 이름입니다.", ephemeral=True)
        return
    
    # 새 계좌번호 생성
    account_number = generate_account_number()
    
    # 공용 계좌 데이터 저장
    public_accounts[계좌이름] = {
        "account_number": account_number,
        "password": 패스워드,
        "balance": 초기잔액,
        "created_at": datetime.now().isoformat(),
        "created_by": interaction.user.id
    }
    save_public_accounts(public_accounts)
    
    # 일반 계좌 목록에도 추가 (잔액 관리 통합)
    users = load_users()
    users[account_number] = {
        "이름": f"[공용] {계좌이름}",
        "계좌번호": account_number,
        "잔액": 초기잔액,
        "공용계좌": True
    }
    save_users(users)
    
    # 거래 내역 추가
    if 초기잔액 > 0:
        add_transaction("공용계좌생성", "ADMIN", account_number, 초기잔액, 0, f"공용 계좌 '{계좌이름}' 생성")
    
    embed = discord.Embed(title="🏦 공용 계좌 생성 완료", color=0x00ff00)
    embed.add_field(name="계좌 이름", value=계좌이름, inline=False)
    embed.add_field(name="계좌번호", value=f"`{account_number}`", inline=False)
    embed.add_field(name="초기 잔액", value=f"{format_number_4digit(초기잔액)}원", inline=False)
    embed.add_field(name="생성 시간", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="공용송금", description="공용 계좌에서 송금합니다 (패스워드 필요)")
async def public_transfer(interaction: discord.Interaction, 계좌번호: str, 패스워드: str, 받는계좌: str, 금액: int, 메모: str = ""):
    # 공용 계좌 인증
    account_name = verify_public_account(계좌번호, 패스워드)
    if not account_name:
        await interaction.response.send_message("❌ 잘못된 공용 계좌 정보입니다.", ephemeral=True)
        return
    
    users = load_users()
    if 받는계좌 not in users:
        await interaction.response.send_message("❌ 존재하지 않는 받는 계좌번호입니다.", ephemeral=True)
        return
    
    if 계좌번호 == 받는계좌:
        await interaction.response.send_message("❌ 같은 계좌로는 송금할 수 없습니다.", ephemeral=True)
        return
    
    if 금액 <= 0:
        await interaction.response.send_message("❌ 송금 금액은 0보다 커야 합니다.", ephemeral=True)
        return
    
    # 계좌 동결 확인
    if is_account_frozen(계좌번호):
        await interaction.response.send_message("❌ 송금 계좌가 동결되어 송금할 수 없습니다.", ephemeral=True)
        return
    
    if is_account_frozen(받는계좌):
        await interaction.response.send_message("❌ 수취 계좌가 동결되어 송금할 수 없습니다.", ephemeral=True)
        return
    
    sender_data = users[계좌번호]
    recipient_data = users[받는계좌]
    
    # 수수료 계산
    fee = calculate_transaction_fee(금액)
    total_amount = 금액 + fee
    
    # 잔액 확인
    if sender_data["잔액"] < total_amount:
        await interaction.response.send_message(
            f"❌ 잔액이 부족합니다.\n현재 잔액: {format_number_4digit(sender_data['잔액'])}원\n필요 금액: {format_number_4digit(total_amount)}원 (송금액: {format_number_4digit(금액)}원 + 수수료: {format_number_4digit(fee)}원)", 
            ephemeral=True
        )
        return
    
    # 송금 실행
    sender_data["잔액"] -= total_amount
    recipient_data["잔액"] += 금액
    save_users(users)
    
    # 공용 계좌 잔액도 업데이트
    public_accounts = load_public_accounts()
    public_accounts[account_name]["balance"] = sender_data["잔액"]
    save_public_accounts(public_accounts)
    
    # 거래 내역 추가
    add_transaction("공용송금", 계좌번호, 받는계좌, 금액, fee, 메모)
    
    embed = discord.Embed(title="🏦 공용 계좌 송금 완료", color=0x00ff00)
    embed.add_field(name="송금 계좌", value=f"{account_name} (`{계좌번호}`)", inline=False)
    embed.add_field(name="수취인", value=f"{recipient_data['이름']} (`{받는계좌}`)", inline=False)
    embed.add_field(name="송금액", value=f"{format_number_4digit(금액)}원", inline=True)
    embed.add_field(name="수수료", value=f"{format_number_4digit(fee)}원", inline=True)
    embed.add_field(name="총 차감액", value=f"{format_number_4digit(total_amount)}원", inline=True)
    embed.add_field(name="송금 계좌 잔액", value=f"{format_number_4digit(sender_data['잔액'])}원", inline=True)
    embed.add_field(name="수취인 잔액", value=f"{format_number_4digit(recipient_data['잔액'])}원", inline=True)
    if 메모:
        embed.add_field(name="메모", value=메모, inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="거래내역", description="최근 거래 내역을 확인합니다")
async def transaction_history(interaction: discord.Interaction, 개수: int = 10):
    account_number = get_account_number_by_user(interaction.user.id)
    if not account_number:
        await interaction.response.send_message("❌ 계좌가 없습니다. `/계좌생성` 명령어로 먼저 계좌를 만드세요.", ephemeral=True)
        return
    
    if 개수 < 1 or 개수 > 50:
        await interaction.response.send_message("❌ 조회할 거래 개수는 1~50 사이여야 합니다.", ephemeral=True)
        return
    
    transactions = load_transactions()
    
    # 해당 계좌와 관련된 거래만 필터링
    user_transactions = []
    for tx in reversed(transactions):
        if tx["from_user"] == account_number or tx["to_user"] == account_number:
            user_transactions.append(tx)
            if len(user_transactions) >= 개수:
                break
    
    if not user_transactions:
        await interaction.response.send_message("❌ 거래 내역이 없습니다.", ephemeral=True)
        return
    
    embed = discord.Embed(title="📊 거래 내역", color=0x0099ff)
    
    transaction_list = ""
    for i, tx in enumerate(user_transactions[:개수]):
        timestamp = datetime.fromisoformat(tx["timestamp"]).strftime("%m/%d %H:%M")
        
        # 입금/출금 구분
        if tx["to_user"] == account_number:
            direction = "📥 입금"
            amount_str = f"+{format_number_4digit(tx['amount'])}원"
            other_party = tx["from_user"]
        else:
            direction = "📤 출금"
            amount_str = f"-{format_number_4digit(tx['amount'] + tx['fee'])}원"
            other_party = tx["to_user"]
        
        # 상대방 정보
        users = load_users()
        if other_party == "SYSTEM" or other_party == "ADMIN":
            other_name = other_party
        elif other_party in users:
            other_name = users[other_party]["이름"]
        else:
            other_name = "알 수 없음"
        
        transaction_list += f"`{timestamp}` {direction} {amount_str}\n"
        transaction_list += f"  └ {tx['type']} - {other_name}"
        if tx.get("memo"):
            transaction_list += f" ({tx['memo']})"
        transaction_list += "\n\n"
    
    # 메시지가 너무 길면 분할
    if len(transaction_list) > 1024:
        transaction_list = transaction_list[:1000] + "...\n(내역이 잘렸습니다)"
    
    embed.add_field(name="최근 거래", value=transaction_list or "거래 내역이 없습니다.", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# 관리자 시스템 설정 명령어들
@bot.tree.command(name="수수료설정", description="[관리자] 거래 수수료를 설정합니다")
async def set_transaction_fee(interaction: discord.Interaction, 활성화: bool, 최소금액: int = 0, 수수료율: float = 0.0):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return
    
    if 수수료율 < 0 or 수수료율 > 1:
        await interaction.response.send_message("❌ 수수료율은 0~1 사이 값이어야 합니다. (예: 0.01 = 1%)", ephemeral=True)
        return
    
    settings = load_settings()
    settings["transaction_fee"] = {
        "enabled": 활성화,
        "min_amount": 최소금액,
        "fee_rate": 수수료율
    }
    save_settings(settings)
    
    embed = discord.Embed(title="💰 수수료 설정 완료", color=0xffa500)
    embed.add_field(name="수수료 활성화", value="✅ 켜짐" if 활성화 else "❌ 꺼짐", inline=False)
    if 활성화:
        embed.add_field(name="최소 적용 금액", value=f"{format_number_4digit(최소금액)}원", inline=True)
        embed.add_field(name="수수료율", value=f"{수수료율 * 100:.2f}%", inline=True)
        embed.add_field(name="예시", value=f"10,000원 송금 시 {format_number_4digit(int(10000 * 수수료율))}원 수수료", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="세금설정", description="[관리자] 세금 시스템을 설정합니다")
async def set_tax_system(interaction: discord.Interaction, 활성화: bool, 세금률: float = 0.0, 징수주기일: int = 30, 세금명: str = "세금"):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return
    
    if 세금률 < 0 or 세금률 > 1:
        await interaction.response.send_message("❌ 세금률은 0~1 사이 값이어야 합니다. (예: 0.1 = 10%)", ephemeral=True)
        return
    
    if 징수주기일 < 1 or 징수주기일 > 365:
        await interaction.response.send_message("❌ 징수 주기는 1~365일 사이여야 합니다.", ephemeral=True)
        return
    
    settings = load_settings()
    settings["tax_system"] = {
        "enabled": 활성화,
        "rate": 세금률,
        "period_days": 징수주기일,
        "last_collected": None,
        "tax_name": 세금명
    }
    save_settings(settings)
    
    embed = discord.Embed(title="🏛️ 세금 시스템 설정 완료", color=0xffa500)
    embed.add_field(name="세금 시스템", value="✅ 활성화" if 활성화 else "❌ 비활성화", inline=False)
    if 활성화:
        embed.add_field(name="세금 이름", value=세금명, inline=True)
        embed.add_field(name="세금률", value=f"{세금률 * 100:.1f}%", inline=True)
        embed.add_field(name="징수 주기", value=f"{징수주기일}일", inline=True)
        embed.add_field(name="예시", value=f"잔액 100만원에서 {format_number_4digit(int(1000000 * 세금률))}원 징수", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="세금징수", description="[관리자] 즉시 세금을 징수합니다")
async def collect_tax(interaction: discord.Interaction):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return
    
    settings = load_settings()
    tax_config = settings.get("tax_system", {})
    
    if not tax_config.get("enabled"):
        await interaction.response.send_message("❌ 세금 시스템이 비활성화되어 있습니다.", ephemeral=True)
        return
    
    users = load_users()
    tax_rate = tax_config["rate"]
    tax_name = tax_config["tax_name"]
    total_collected = 0
    count = 0
    
    await interaction.response.defer()  # 처리 시간을 위해 지연 응답
    
    for account_number, data in users.items():
        # 동결된 계좌나 공용 계좌는 세금 면제
        if is_account_frozen(account_number) or data.get("공용계좌"):
            continue
        
        if data["잔액"] > 0:
            tax_amount = int(data["잔액"] * tax_rate)
            if tax_amount > 0:
                data["잔액"] -= tax_amount
                total_collected += tax_amount
                count += 1
                
                # 거래 내역 추가
                add_transaction(tax_name, account_number, "SYSTEM", tax_amount, 0, f"{tax_name} 징수")
    
    save_users(users)
    
    # 마지막 징수 시간 업데이트
    settings["tax_system"]["last_collected"] = datetime.now().isoformat()
    save_settings(settings)
    
    embed = discord.Embed(title=f"🏛️ {tax_name} 징수 완료", color=0x00ff00)
    embed.add_field(name="징수 대상", value=f"{count}개 계좌", inline=True)
    embed.add_field(name="총 징수액", value=f"{format_number_4digit(total_collected)}원", inline=True)
    embed.add_field(name="징수율", value=f"{tax_rate * 100:.1f}%", inline=True)
    embed.add_field(name="징수 시간", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    
    await interaction.followup.send(embed=embed)

# 공용계좌 자동완성 함수
async def public_account_autocomplete(interaction: discord.Interaction, current: str):
    """공용계좌 목록 자동완성"""
    public_accounts = load_public_accounts()
    choices = []
    
    for account_name, account_data in public_accounts.items():
        account_number = account_data.get("account_number", "")
        display_name = f"{account_name} ({account_number})"
        
        if current.lower() in display_name.lower():
            choices.append(app_commands.Choice(name=display_name, value=account_name))
        
        if len(choices) >= 25:  # Discord 제한
            break
    
    return choices

@bot.tree.command(name="관리자월급설정", description="[관리자] 사용자의 월급을 설정합니다")
@app_commands.autocomplete(공용계좌=public_account_autocomplete)
async def set_salary(interaction: discord.Interaction, 대상자: discord.Member, 액수: int, 공용계좌: str):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return
    
    if 액수 <= 0:
        await interaction.response.send_message("❌ 월급 액수는 0보다 커야 합니다.", ephemeral=True)
        return
    
    # 대상자 계좌 확인
    target_account = get_account_number_by_user(대상자.id)
    if not target_account:
        await interaction.response.send_message("❌ 대상자가 계좌를 가지고 있지 않습니다.", ephemeral=True)
        return
    
    # 공용계좌 존재 확인
    public_accounts = load_public_accounts()
    if 공용계좌 not in public_accounts:
        await interaction.response.send_message("❌ 존재하지 않는 공용계좌입니다.", ephemeral=True)
        return
    
    source_account_number = public_accounts[공용계좌]["account_number"]
    
    # 설정 저장
    settings = load_settings()
    if "salary_system" not in settings:
        settings["salary_system"] = {"enabled": False, "salaries": {}, "last_paid": None, "source_account": {}}
    
    settings["salary_system"]["salaries"][str(대상자.id)] = {
        "amount": 액수,
        "target_account": target_account,
        "target_name": 대상자.display_name,
        "source_account": 공용계좌,
        "source_account_number": source_account_number
    }
    
    # 월급 시스템 자동 활성화
    settings["salary_system"]["enabled"] = True
    save_settings(settings)
    
    embed = discord.Embed(title="💰 월급 설정 완료", color=0x00ff00)
    embed.add_field(name="대상자", value=f"{대상자.display_name} (`{target_account}`)", inline=False)
    embed.add_field(name="월급액", value=f"{format_number_4digit(액수)}원", inline=True)
    embed.add_field(name="지급 계좌", value=f"{공용계좌} (`{source_account_number}`)", inline=True)
    embed.add_field(name="시스템 상태", value="✅ 활성화됨", inline=True)
    embed.add_field(name="설정 시간", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="월급목록", description="[관리자] 설정된 월급 목록을 확인합니다")
async def list_salaries(interaction: discord.Interaction):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return
    
    settings = load_settings()
    salary_config = settings.get("salary_system", {})
    salaries = salary_config.get("salaries", {})
    
    if not salaries:
        await interaction.response.send_message("❌ 설정된 월급이 없습니다.", ephemeral=True)
        return
    
    embed = discord.Embed(title="💼 월급 목록", color=0x0099ff)
    
    salary_list = ""
    total_amount = 0
    
    for user_id, salary_data in salaries.items():
        target_name = salary_data.get("target_name", "알 수 없음")
        target_account = salary_data.get("target_account", "알 수 없음")
        amount = salary_data.get("amount", 0)
        source_account = salary_data.get("source_account", "알 수 없음")
        
        salary_list += f"👤 {target_name} (`{target_account}`)\n"
        salary_list += f"  └ {format_number_4digit(amount)}원 (출처: {source_account})\n\n"
        total_amount += amount
    
    # 메시지가 너무 길면 분할
    if len(salary_list) > 1024:
        salary_list = salary_list[:1000] + "...\n(목록이 잘렸습니다)"
    
    embed.add_field(name="월급 대상자", value=salary_list, inline=False)
    embed.add_field(name="총 대상자 수", value=f"{len(salaries)}명", inline=True)
    embed.add_field(name="월 총 지급액", value=f"{format_number_4digit(total_amount)}원", inline=True)
    
    system_status = "✅ 활성화" if salary_config.get("enabled") else "❌ 비활성화"
    embed.add_field(name="시스템 상태", value=system_status, inline=True)
    
    last_paid = salary_config.get("last_paid")
    if last_paid:
        last_paid_date = datetime.fromisoformat(last_paid).strftime("%Y-%m-%d %H:%M:%S")
        embed.add_field(name="마지막 지급", value=last_paid_date, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="월급지급", description="[관리자] 설정된 모든 월급을 즉시 지급합니다")
async def pay_salaries(interaction: discord.Interaction):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return
    
    settings = load_settings()
    salary_config = settings.get("salary_system", {})
    
    if not salary_config.get("enabled"):
        await interaction.response.send_message("❌ 월급 시스템이 비활성화되어 있습니다.", ephemeral=True)
        return
    
    salaries = salary_config.get("salaries", {})
    if not salaries:
        await interaction.response.send_message("❌ 설정된 월급이 없습니다.", ephemeral=True)
        return
    
    await interaction.response.defer()  # 처리 시간을 위해 지연 응답
    
    users = load_users()
    public_accounts = load_public_accounts()
    success_count = 0
    error_count = 0
    total_paid = 0
    error_messages = []
    
    for user_id, salary_data in salaries.items():
        try:
            target_account = salary_data["target_account"]
            amount = salary_data["amount"]
            source_account_name = salary_data["source_account"]
            source_account_number = salary_data["source_account_number"]
            target_name = salary_data["target_name"]
            
            # 계좌 존재 확인
            if target_account not in users or source_account_number not in users:
                error_messages.append(f"{target_name}: 계좌를 찾을 수 없음")
                error_count += 1
                continue
            
            # 계좌 동결 확인
            if is_account_frozen(target_account):
                error_messages.append(f"{target_name}: 수취 계좌가 동결됨")
                error_count += 1
                continue
            
            if is_account_frozen(source_account_number):
                error_messages.append(f"{target_name}: 지급 계좌가 동결됨")
                error_count += 1
                continue
            
            # 잔액 확인
            source_balance = users[source_account_number]["잔액"]
            if source_balance < amount:
                error_messages.append(f"{target_name}: 지급 계좌 잔액 부족")
                error_count += 1
                continue
            
            # 월급 지급 실행
            users[source_account_number]["잔액"] -= amount
            users[target_account]["잔액"] += amount
            
            # 공용계좌 잔액도 업데이트
            if source_account_name in public_accounts:
                public_accounts[source_account_name]["balance"] = users[source_account_number]["잔액"]
            
            # 거래 내역 추가
            add_transaction("월급", source_account_number, target_account, amount, 0, f"{target_name} 월급 지급")
            
            success_count += 1
            total_paid += amount
            
        except Exception as e:
            error_messages.append(f"{salary_data.get('target_name', '알 수 없음')}: 처리 중 오류")
            error_count += 1
    
    # 데이터 저장
    save_users(users)
    save_public_accounts(public_accounts)
    
    # 마지막 지급 시간 업데이트
    settings["salary_system"]["last_paid"] = datetime.now().isoformat()
    save_settings(settings)
    
    embed = discord.Embed(title="💰 월급 지급 완료", color=0x00ff00)
    embed.add_field(name="성공", value=f"{success_count}명", inline=True)
    embed.add_field(name="실패", value=f"{error_count}명", inline=True)
    embed.add_field(name="총 지급액", value=f"{format_number_4digit(total_paid)}원", inline=True)
    embed.add_field(name="지급 시간", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=False)
    
    if error_messages:
        error_text = "\n".join(error_messages[:5])  # 최대 5개만 표시
        if len(error_messages) > 5:
            error_text += f"\n... 외 {len(error_messages) - 5}건"
        embed.add_field(name="오류 내역", value=error_text, inline=False)
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="월급삭제", description="[관리자] 특정 사용자의 월급 설정을 삭제합니다")
async def remove_salary(interaction: discord.Interaction, 대상자: discord.Member):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return
    
    settings = load_settings()
    salary_config = settings.get("salary_system", {})
    salaries = salary_config.get("salaries", {})
    
    user_id_str = str(대상자.id)
    if user_id_str not in salaries:
        await interaction.response.send_message("❌ 해당 사용자의 월급 설정이 없습니다.", ephemeral=True)
        return
    
    # 월급 설정 삭제
    removed_salary = salaries.pop(user_id_str)
    save_settings(settings)
    
    embed = discord.Embed(title="🗑️ 월급 설정 삭제 완료", color=0xff6b6b)
    embed.add_field(name="대상자", value=대상자.display_name, inline=False)
    embed.add_field(name="삭제된 월급액", value=f"{format_number_4digit(removed_salary['amount'])}원", inline=True)
    embed.add_field(name="삭제 시간", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=True)
    
    await interaction.response.send_message(embed=embed)

# 가명 추출 함수 (기존 닉네임 형식에서 가명 부분 추출)
def extract_alias_from_name(name: str) -> str:
    """이름에서 가명 추출 ([역할] 가명 | 닉네임 형식에서 가명 부분)"""
    try:
        if "|" in name:
            # [역할] 가명 | 닉네임 형식인 경우
            parts = name.split("|")
            if len(parts) >= 2:
                left_part = parts[0].strip()
                if "]" in left_part:
                    # [역할] 가명 부분에서 가명만 추출
                    role_and_alias = left_part.split("]", 1)
                    if len(role_and_alias) >= 2:
                        return role_and_alias[1].strip()
        # 형식에 맞지 않으면 원래 이름 반환
        return name
    except:
        return name

@bot.tree.command(name="엑셀내보내기", description="[관리자] 거래내역을 엑셀 파일로 내보냅니다")
async def export_excel(
    interaction: discord.Interaction,
    사용자1: Optional[discord.Member] = None,
    사용자2: Optional[discord.Member] = None,
    사용자3: Optional[discord.Member] = None,
    사용자4: Optional[discord.Member] = None,
    사용자5: Optional[discord.Member] = None,
    전체내보내기: bool = False
):
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)
        return
    
    # 처리 시간을 위해 지연 응답
    await interaction.response.defer(ephemeral=True)
    
    try:
        # 대상 사용자들 수집
        target_users = []
        if not 전체내보내기:
            for user in [사용자1, 사용자2, 사용자3, 사용자4, 사용자5]:
                if user is not None:
                    account_number = get_account_number_by_user(user.id)
                    if account_number:
                        target_users.append(account_number)
            
            if not target_users:
                await interaction.followup.send("❌ 선택된 사용자 중 계좌가 있는 사용자가 없습니다.", ephemeral=True)
                return
        
        # 거래내역 로드
        transactions = load_transactions()
        users = load_users()
        
        # 필터링할 거래내역 선택
        filtered_transactions = []
        if 전체내보내기:
            filtered_transactions = transactions
        else:
            for tx in transactions:
                if tx["from_user"] in target_users or tx["to_user"] in target_users:
                    filtered_transactions.append(tx)
        
        if not filtered_transactions:
            await interaction.followup.send("❌ 해당 조건에 맞는 거래내역이 없습니다.", ephemeral=True)
            return
        
        # 엑셀 데이터 준비
        excel_data = []
        
        for tx in filtered_transactions:
            # 날짜/시간 분리
            timestamp = datetime.fromisoformat(tx["timestamp"])
            date_str = timestamp.strftime("%Y-%m-%d")
            time_str = timestamp.strftime("%H:%M:%S")
            
            # 송금자 정보
            from_user = tx["from_user"]
            if from_user == "SYSTEM" or from_user == "ADMIN":
                sender_name = from_user
                sender_alias = from_user
            elif from_user in users:
                sender_name = users[from_user]["이름"]
                sender_alias = extract_alias_from_name(sender_name)
            else:
                sender_name = "알 수 없음"
                sender_alias = "알 수 없음"
            
            # 수금자 정보
            to_user = tx["to_user"]
            if to_user == "SYSTEM" or to_user == "ADMIN":
                receiver_name = to_user
                receiver_alias = to_user
            elif to_user in users:
                receiver_name = users[to_user]["이름"]
                receiver_alias = extract_alias_from_name(receiver_name)
            else:
                receiver_name = "알 수 없음"
                receiver_alias = "알 수 없음"
            
            # ---- PATCH: CSV 병합 명령어 더 안전하게 ----
@bot.tree.command(name="관리자데이터병합", description="[관리자] CSV 업로드로 계좌 잔액을 갱신합니다.")
async def admin_import_csv(
    interaction: discord.Interaction,
    파일: discord.Attachment,
    create_missing: Optional[bool] = False
):
    # 0) 관리자 체크
    if not is_admin(interaction.user.id):
        if not interaction.response.is_done():
            await interaction.response.send_message("관리자만 사용 가능합니다.", ephemeral=True)
        else:
            await interaction.followup.send("관리자만 사용 가능합니다.", ephemeral=True)
        return

    # 1) 즉시 지연응답(3초 제한 회피)
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True, thinking=True)
    except Exception:
        # 이미 응답된 상태일 수 있음 → 무시
        pass

    # 2) 확장자/크기 체크
    if not (파일.filename.lower().endswith(".csv")):
        msg = "CSV 파일만 지원합니다. (확장자 .csv)"
        try:
            await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            # 응답 토큰 만료 대비
            pass
        return

    # 3) 파일 읽기
    try:
        raw = await 파일.read()
        text = raw.decode("utf-8", errors="ignore")
    except Exception as e:
        err = f"파일을 읽는 중 오류가 발생했습니다: {e}"
        try:
            await interaction.followup.send(err, ephemeral=True)
        except Exception:
            pass
        return

    # 4) CSV 파싱(판다스 → 실패시 csv 모듈)
    import io, csv as _csv
    rows = []
    parse_error = None
    try:
        df = pd.read_csv(io.StringIO(text))
        rows = df.to_dict(orient="records")
    except Exception as e:
        try:
            reader = _csv.DictReader(io.StringIO(text))
            rows = list(reader)
        except Exception as e2:
            parse_error = f"CSV 파싱 실패: {e2}"

    if parse_error:
        try:
            await interaction.followup.send(parse_error, ephemeral=True)
        except Exception:
            pass
        return
    if not rows:
        try:
            await interaction.followup.send("CSV에 데이터가 없습니다.", ephemeral=True)
        except Exception:
            pass
        return

    # 5) 키 정규화
    def norm_key(k: str) -> str:
        k = (k or "").strip().lower()
        mapping = {
            "계좌번호": "account_number", "account_number": "account_number", "account": "account_number", "계좌": "account_number",
            "잔액": "balance", "balance": "balance", "잔고": "balance",
            "이름": "name", "name": "name"
        }
        return mapping.get(k, k)

    users = load_users()
    created = updated = skipped = 0
    errors = []

    # 6) 병합 로직
    for idx, row in enumerate(rows, start=1):
        try:
            normalized = {norm_key(k): v for k, v in row.items()}
            acc = normalized.get("account_number")
            bal = normalized.get("balance")
            name = normalized.get("name")

            if acc is None or bal is None:
                skipped += 1
                continue

            acc = str(acc).strip()
            # balance 숫자화
            try:
                bal = int(float(str(bal).replace(",", "")))
            except Exception:
                skipped += 1
                continue

            if acc not in users:
                if create_missing:
                    users[acc] = {"이름": str(name or f"사용자({acc})"), "계좌번호": acc, "잔액": bal}
                    created += 1
                else:
                    skipped += 1
                    continue
            else:
                users[acc]["잔액"] = bal
                if name:
                    users[acc]["이름"] = str(name)
                updated += 1

        except Exception as e:
            skipped += 1
            errors.append(f"{idx}행 처리 실패: {e}")

    # 7) 저장 및 결과 회신
    try:
        save_users(users)
        embed = discord.Embed(title="📥 DB 갱신 결과", color=0x00b894)
        embed.add_field(name="업데이트", value=f"{updated}건", inline=True)
        embed.add_field(name="신규 생성", value=f"{created}건", inline=True)
        embed.add_field(name="스킵", value=f"{skipped}건", inline=True)
        if errors:
            # 최대 5건만 표시
            msg = "\n".join(errors[:5])
            if len(errors) > 5:
                msg += f"\n... 외 {len(errors) - 5}건"
            embed.add_field(name="오류 일부", value=msg, inline=False)

        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        # “Unknown interaction” 방지: 응답 경로 분기
        msg = f"저장/응답 중 오류: {e}"
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass


            # 엑셀 행 데이터
            row_data = {
                "날짜": date_str,
                "시간": time_str,
                "거래유형": tx["type"],
                "송금자 계좌번호": from_user,
                "송금자 이름": sender_name,
                "송금자 가명": sender_alias,
                "수금자 계좌번호": to_user,
                "수금자 이름": receiver_name,
                "수금자 가명": receiver_alias,
                "거래금액": tx["amount"],
                "수수료": tx["fee"],
                "메모": tx.get("memo", "")
            }
            excel_data.append(row_data)
        
        # pandas DataFrame 생성
        df = pd.DataFrame(excel_data)
        
        # 엑셀 파일 생성
        filename = f"거래내역_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = f"/tmp/{filename}"
        
        # 엑셀 파일로 저장
        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='거래내역', index=False)
            
            # 워크시트 스타일 조정
            workbook = writer.book
            worksheet = writer.sheets['거래내역']
            
            # 열 너비 조정
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)  # 최대 50자로 제한
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        # 디스코드 파일 전송
        with open(filepath, 'rb') as f:
            discord_file = discord.File(f, filename)
            
            embed = discord.Embed(title="📊 거래내역 엑셀 내보내기 완료", color=0x00ff00)
            
            if 전체내보내기:
                embed.add_field(name="내보내기 범위", value="전체 거래내역", inline=False)
            else:
                user_names = []
                for user in [사용자1, 사용자2, 사용자3, 사용자4, 사용자5]:
                    if user is not None:
                        user_names.append(user.display_name)
                embed.add_field(name="대상 사용자", value=", ".join(user_names), inline=False)
            
            embed.add_field(name="총 거래 수", value=f"{len(filtered_transactions)}건", inline=True)
            embed.add_field(name="파일명", value=filename, inline=True)
            embed.add_field(name="생성 시간", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), inline=True)
            
            await interaction.followup.send(embed=embed, file=discord_file, ephemeral=True)
        
        # 임시 파일 삭제
        import os
        if os.path.exists(filepath):
            os.remove(filepath)
    
    except Exception as e:
        embed = discord.Embed(title="❌ 엑셀 내보내기 실패", color=0xff0000)
        embed.add_field(name="오류", value=f"파일 생성 중 오류가 발생했습니다: {str(e)}", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN이 설정되지 않았습니다. .env 파일을 확인하세요.")
    else:
        print(f"✅ DISCORD_TOKEN이 로드되었습니다. 길이: {len(TOKEN)} 문자")
        if TOKEN.strip() != TOKEN:
            print("⚠️ 토큰에 공백이 포함되어 있습니다. 제거합니다.")
            TOKEN = TOKEN.strip()
        if not TOKEN.startswith(('Bot ', 'bot ')):
            print("ℹ️ 토큰이 'Bot ' 접두사를 포함하지 않습니다.")
        try:
            bot.run(TOKEN)
        except discord.LoginFailure as e:
            print(f"❌ 로그인 실패: {e}")
            print("토큰이 유효하지 않거나 만료되었을 수 있습니다.")
            print("Discord Developer Portal에서 새 토큰을 생성하세요.")
        except Exception as e:
            print(f"❌ 예상치 못한 오류: {e}")
            