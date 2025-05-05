# dashboard/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger # Import Paginator
import logging

# Import models from other apps
from orders.models import Order, OrderItem
# Import Wallet models and get_or_create shortcut
from wallet.models import Wallet, WalletTransaction

logger = logging.getLogger(__name__)

@login_required
def dashboard_view(request):
    """
    Displays a dashboard with user-specific information (recent items).
    Ensures wallet exists for the logged-in user.
    """
    user = request.user
    context = {}
    wallet = None

    try:
        # 1. Get Wallet (Create if it doesn't exist)
        wallet, created = Wallet.objects.get_or_create(user=user)
        if created:
            logger.info(f"Wallet created automatically for user {user.email} on dashboard access.")
        context['wallet'] = wallet # Add wallet to context

        # Get Recent Wallet Transactions (limited)
        try:
            wallet_transactions = WalletTransaction.objects.filter(
                wallet=wallet
            ).order_by('-timestamp')[:5] # Show 5 recent items
            context['wallet_transactions'] = wallet_transactions
        except Exception as tx_e:
             logger.error(f"Error fetching wallet transactions: {tx_e}", exc_info=True)
             context['wallet_transactions'] = []; context['wallet_error'] = "Could not load transactions."

        # 2. Get Recent Orders placed by the user (limited)
        my_orders = Order.objects.filter(
            buyer=user
        ).prefetch_related('items').order_by('-created_at')[:5]
        context['my_orders'] = my_orders

        # 3. Get Recent Items sold by the user (limited)
        sold_items = OrderItem.objects.filter(
            seller=user,
            order__status='PAID'
        ).select_related('order', 'product', 'order__buyer').order_by('-order__created_at')[:5]
        context['sold_items'] = sold_items

    except Exception as e:
        logger.error(f"Error fetching dashboard data for user {user.email}: {e}", exc_info=True)
        messages.error(request, "There was an error loading your dashboard data.")
        context['dashboard_error'] = "Could not load dashboard data."
        context.setdefault('my_orders', [])
        context.setdefault('sold_items', [])
        context.setdefault('wallet', wallet) # Pass wallet even if tx failed
        context.setdefault('wallet_transactions', [])

    return render(request, 'dashboard/dashboard.html', context)


# --- Views for "View All" pages ---

@login_required
def all_wallet_transactions(request):
    """Displays all wallet transactions for the logged-in user with pagination."""
    # Use get_or_create here too, in case user navigates directly
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    transaction_list = WalletTransaction.objects.filter(wallet=wallet).order_by('-timestamp')

    paginator = Paginator(transaction_list, 20) # Show 20 transactions per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number) # Handles invalid page numbers gracefully

    context = {
        'wallet': wallet,
        'page_obj': page_obj,
        'is_paginated': paginator.num_pages > 1
    }
    return render(request, 'dashboard/all_transactions.html', context)


@login_required
def all_my_orders(request):
    """Displays all orders placed by the logged-in user with pagination."""
    order_list = Order.objects.filter(
        buyer=request.user
    ).prefetch_related('items').order_by('-created_at')

    paginator = Paginator(order_list, 15) # Show 15 orders per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'is_paginated': paginator.num_pages > 1,
        'list_type': 'My Purchases'
    }
    return render(request, 'dashboard/all_my_orders.html', context)

@login_required
def all_sales_history(request):
    """Displays all items sold by the logged-in user from PAID orders with pagination."""
    sold_items_list = OrderItem.objects.filter(
        seller=request.user,
        order__status='PAID'
    ).select_related(
        'order', 'product', 'order__buyer'
    ).order_by('-order__created_at')

    paginator = Paginator(sold_items_list, 20) # Show 20 sold items per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'is_paginated': paginator.num_pages > 1
    }
    return render(request, 'dashboard/all_sales_history.html', context)