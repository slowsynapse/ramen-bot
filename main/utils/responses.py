MESSAGES = {}


MESSAGES['deposit'] = """Depositing SPICE will credit your account with equivalent SPICE points you can use for tipping other users.
\nTo proceed with deposit, you have to run this command again but include the SLP address where you <b>send</b> your SPICE <b>from</b>. The syntax is `/deposit your_slp_address`.
\n\nExample:
\n/deposit simpleledger:qpgje2ycwhh2rn8v0rg5r7d8lgw2pp84zgpkd6wyer
\n\nThe bot will respond with an SLP address where you need to deposit SPICE. You can then deposit SPICE to that address any amount anytime.
\n\nImportant note!!! Make sure you only deposit SPICE token from the SLP address you registered in the deposit command. Otherwise, the SPICE you send will not be credited.
"""

MESSAGES['withdraw'] = """Withdrawing converts your SPICE Points to (Gifted) SPICE SLP Tokens. (Check /FAQs to learn more about gifted SPICE SLP Tokens)
\n\nThe proper syntax is:
\n/withdraw "amount" "simpleledger_address"
\n\nExample:
\n/withdraw 10 simpleledger:qpgje2ycwhh2rn8v0rg5r7d8lgw2pp84zgpkd6wyer
"""
MESSAGES['rain'] = """To rain SPICE, simply type the following commands in any group that has Spicebot:
\n**Examples:**\n
rain 5 people 100 spice each\n(100 spice to each of 5 people)\n\n
rain 5 people 500 spice total\n(divides 500 spice in total between 5 people)\n\n
rain 5 people 100 spice\n(defaults to "each". 5 people would get 100 spice each)\n\n\nOR\n\n
**Examples:**\n\nrain 5 people 100 spice each 3/5 pof\n\nrain 5 people 500 spice total 3/5 pof
\n\nMinimum amount of Spice in total to invoke rain = 500 Spice"""
def get_response(key, bot='twitter'):
    if key in MESSAGES.keys():
        return MESSAGES[key]
