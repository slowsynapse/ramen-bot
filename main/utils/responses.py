MESSAGES = {}


MESSAGES['deposit'] = """Depositing CHIP tokens will credit your account with equivalent CHIP points you can use for tipping other users.
\nTo deposit, send CHIP tokens to your CashToken address. Use the /deposit command to see your deposit address.
\n\nYour deposited CHIP tokens will be converted to CHIP points automatically.
"""

MESSAGES['withdraw'] = """Withdrawals are currently disabled.
\n\nWhen withdrawals are enabled, you will be able to convert your CHIP Points to CHIP Tokens (CashTokens).
"""
MESSAGES['rain'] = """To rain CHIP, simply type the following commands in any group that has ChipBot:
\n**Examples:**\n
rain 5 people 100 chip each\n(100 chip to each of 5 people)\n\n
rain 5 people 500 chip total\n(divides 500 chip in total between 5 people)\n\n
rain 5 people 100 chip\n(defaults to "each". 5 people would get 100 chip each)\n\n\nOR\n\n
**Examples:**\n\nrain 5 people 100 chip each 3/5 pof\n\nrain 5 people 500 chip total 3/5 pof
\n\nMinimum amount of CHIP in total to invoke rain = 500 CHIP"""
def get_response(key, bot='twitter'):
    if key in MESSAGES.keys():
        return MESSAGES[key]
