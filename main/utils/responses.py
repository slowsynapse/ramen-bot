MESSAGES = {}


MESSAGES['deposit'] = """Depositing RAMEN tokens will credit your account with equivalent RAMEN points you can use for tipping other users.
\nTo deposit, send RAMEN tokens to your CashToken address. Use the /deposit command to see your deposit address.
\n\nYour deposited RAMEN tokens will be converted to RAMEN points automatically.
"""

MESSAGES['withdraw'] = """Withdrawals are currently disabled.
\n\nWhen withdrawals are enabled, you will be able to convert your RAMEN Points to RAMEN Tokens (CashTokens).
"""
MESSAGES['rain'] = """To rain RAMEN, simply type the following commands in any group that has RamenBot:
\n**Examples:**\n
rain 5 people 100 ramen each\n(100 ramen to each of 5 people)\n\n
rain 5 people 500 ramen total\n(divides 500 ramen in total between 5 people)\n\n
rain 5 people 100 ramen\n(defaults to "each". 5 people would get 100 ramen each)\n\n\nOR\n\n
**Examples:**\n\nrain 5 people 100 ramen each 3/5 pof\n\nrain 5 people 500 ramen total 3/5 pof
\n\nMinimum amount of RAMEN in total to invoke rain = 500 RAMEN"""
def get_response(key, bot='twitter'):
    if key in MESSAGES.keys():
        return MESSAGES[key]
