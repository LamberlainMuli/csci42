from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
import json
from django.http import FileResponse
from .models import UserOutfit, OutfitItem
from marketplace.models import Product
from .image_generator import generate_outfit_image

BASE_WIDTH = 80  # base container width at scale=1

@login_required
def create_outfit(request, outfit_id=None):
    """
    Handles both creation and re-creation of an outfit.
    If outfit_id is provided, the existing outfit's items are pre-loaded.
    """
    if outfit_id:
        outfit = get_object_or_404(UserOutfit, id=outfit_id, user=request.user)
    else:
        outfit = None

    if request.method == 'POST':
        outfit_data = json.loads(request.POST.get('outfit_data', '[]'))
        if outfit:
            outfit.items.all().delete()
        else:
            outfit = UserOutfit.objects.create(user=request.user)

        for item in outfit_data:
            OutfitItem.objects.create(
                outfit=outfit,
                product_id=item['product_id'],
                position_x=item['x'],
                position_y=item['y'],
                scale=item['scale'],
                z_index=item.get('z_index', 0)
            )
        return redirect('mix_and_match:preview_outfit', outfit_id=outfit.id)
    else:
        available_items = Product.objects.filter(
            Q(is_public=True) | Q(seller=request.user, is_public=False)
        ).distinct()

        # Attach a primary_image to each product if it exists, else fallback
        for item in available_items:
            item.primary_image = item.images.filter(is_primary=True).first() or item.images.first()

        context = {
            'available_items': available_items,
            'outfit': outfit,
            'outfit_items': outfit.items.all() if outfit else []
        }
        return render(request, 'mix_and_match/create_outfit.html', context)

@login_required
def edit_outfit(request, outfit_id):
    """
    Dedicated view for editing an existing outfit.
    Reuses create_outfit logic with an outfit_id.
    """
    return create_outfit(request, outfit_id=outfit_id)

@login_required
def preview_outfit(request, outfit_id):
    """
    Show the final outfit. We replicate the "base 80 px" approach:
    final_width = 80 * scale. Then place the item at (x, y).
    """
    outfit = get_object_or_404(UserOutfit, id=outfit_id, user=request.user)
    outfit_items = []
    for item in outfit.items.all():
        # Primary image fallback
        primary = item.product.images.filter(is_primary=True).first()
        if primary:
            item.primary_image_url = primary.image.url
        else:
            if item.product.images.exists():
                item.primary_image_url = item.product.images.first().image.url
            else:
                item.primary_image_url = '/static/images/placeholder.png'

        # We'll store final_width so the template can do width: final_width px
        item.final_width = BASE_WIDTH * item.scale
        # We'll keep the same top/left logic as creation. If the user placed the item at (x, y),
        # we apply that in absolute terms. The bounding in creation was within 0..(canvas width - final_width).
        outfit_items.append(item)

    context = {
        'outfit': outfit,
        'outfit_items': outfit_items
    }
    return render(request, 'mix_and_match/preview_outfit.html', context)

@login_required
def download_outfit(request, outfit_id):
    """
    Generate and return the composite PNG image for the outfit.
    """
    outfit = get_object_or_404(UserOutfit, id=outfit_id, user=request.user)
    output = generate_outfit_image(outfit)
    filename = f"outfit_{outfit.id}.png"
    return FileResponse(output, as_attachment=True, filename=filename)

@login_required
def recommendations(request):
    category = request.GET.get('category')
    condition = request.GET.get('condition')
    recommended_items = Product.objects.filter(is_public=True)
    if category:
        recommended_items = recommended_items.filter(category=category)
    if condition:
        recommended_items = recommended_items.filter(condition=condition)
    recommended_items = recommended_items.order_by('?')[:10]

    categories = Product.objects.filter(is_public=True).values_list('category', flat=True).distinct()
    conditions = Product.objects.filter(is_public=True).values_list('condition', flat=True).distinct()

    context = {
        'recommended_items': recommended_items,
        'categories': categories,
        'conditions': conditions,
        'current_category': category,
        'current_condition': condition,
    }
    return render(request, 'mix_and_match/recommendations.html', context)
