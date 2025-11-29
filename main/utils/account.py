from main.models import Transaction


def compute_balance(user_id):
    # Get incoming and outgoing transactions
    incoming_trans = Transaction.objects.filter(
        user_id=user_id,
        transaction_type__icontains="Incoming"
    )
    incoming_trans_sum = 0
    for trans in incoming_trans:
        incoming_trans_sum += trans.amount
    
    outgoing_trans = Transaction.objects.filter(
        user_id=user_id, 
        transaction_type__icontains="Outgoing"
    )
    outgoing_trans_sum = 0
    for trans in outgoing_trans:
        outgoing_trans_sum += trans.amount

    # Return balance as difference between incoming and outgoing transaction sum
    return incoming_trans_sum - outgoing_trans_sum
