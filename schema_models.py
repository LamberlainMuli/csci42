# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class AuthGroup(models.Model):
    name = models.CharField(unique=True, max_length=150)

    class Meta:
        managed = False
        db_table = 'auth_group'


class AuthGroupPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
    permission = models.ForeignKey('AuthPermission', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_group_permissions'
        unique_together = (('group', 'permission'),)


class AuthPermission(models.Model):
    name = models.CharField(max_length=255)
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
    codename = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'auth_permission'
        unique_together = (('content_type', 'codename'),)


class CartCart(models.Model):
    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField()
    user = models.OneToOneField('UserCustomuser', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'cart_cart'


class CartCartitem(models.Model):
    id = models.BigAutoField(primary_key=True)
    quantity = models.IntegerField()
    added_at = models.DateTimeField()
    cart = models.ForeignKey(CartCart, models.DO_NOTHING)
    product = models.ForeignKey('MarketplaceProduct', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'cart_cartitem'


class CartSaveditem(models.Model):
    id = models.BigAutoField(primary_key=True)
    saved_at = models.DateTimeField()
    product = models.ForeignKey('MarketplaceProduct', models.DO_NOTHING)
    user = models.ForeignKey('UserCustomuser', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'cart_saveditem'


class DjangoAdminLog(models.Model):
    action_time = models.DateTimeField()
    object_id = models.TextField(blank=True, null=True)
    object_repr = models.CharField(max_length=200)
    action_flag = models.SmallIntegerField()
    change_message = models.TextField()
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey('UserCustomuser', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_admin_log'


class DjangoContentType(models.Model):
    app_label = models.CharField(max_length=100)
    model = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'django_content_type'
        unique_together = (('app_label', 'model'),)


class DjangoMigrations(models.Model):
    id = models.BigAutoField(primary_key=True)
    app = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    applied = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_migrations'


class DjangoSession(models.Model):
    session_key = models.CharField(primary_key=True, max_length=40)
    session_data = models.TextField()
    expire_date = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_session'


class ImageScanningProcessedclothingitem(models.Model):
    id = models.BigAutoField(primary_key=True)
    processed_image = models.CharField(max_length=100)
    created_at = models.DateTimeField()
    product = models.ForeignKey('MarketplaceProduct', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey('UserCustomuser', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'image_scanning_processedclothingitem'


class ImageScanningUploadedimage(models.Model):
    id = models.BigAutoField(primary_key=True)
    original_image = models.CharField(max_length=100)
    upload_date = models.DateTimeField()
    user = models.ForeignKey('UserCustomuser', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'image_scanning_uploadedimage'


class MarketplaceProduct(models.Model):
    id = models.BigAutoField(primary_key=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    size = models.CharField(max_length=20, blank=True, null=True)
    color = models.CharField(max_length=50, blank=True, null=True)
    material = models.CharField(max_length=100, blank=True, null=True)
    category = models.CharField(max_length=20, blank=True, null=True)
    condition = models.CharField(max_length=3, blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    is_sold = models.BooleanField()
    seller = models.ForeignKey('UserCustomuser', models.DO_NOTHING)
    is_public = models.BooleanField()
    quantity = models.IntegerField()

    class Meta:
        managed = False
        db_table = 'marketplace_product'


class MarketplaceProductimage(models.Model):
    id = models.BigAutoField(primary_key=True)
    image = models.CharField(max_length=100)
    is_primary = models.BooleanField()
    product = models.ForeignKey(MarketplaceProduct, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'marketplace_productimage'


class MixAndMatchOutfitairesult(models.Model):
    id = models.BigAutoField(primary_key=True)
    generated = models.CharField(max_length=100)
    critique = models.TextField()
    created_at = models.DateTimeField()
    outfit = models.OneToOneField('MixAndMatchUseroutfit', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'mix_and_match_outfitairesult'


class MixAndMatchOutfititem(models.Model):
    id = models.BigAutoField(primary_key=True)
    position_x = models.FloatField()
    position_y = models.FloatField()
    scale = models.FloatField()
    z_index = models.IntegerField()
    outfit = models.ForeignKey('MixAndMatchUseroutfit', models.DO_NOTHING)
    product = models.ForeignKey(MarketplaceProduct, models.DO_NOTHING)
    modified_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'mix_and_match_outfititem'


class MixAndMatchOutfitrecommendation(models.Model):
    id = models.BigAutoField(primary_key=True)
    criteria = models.TextField()
    created_at = models.DateTimeField()
    user = models.ForeignKey('UserCustomuser', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'mix_and_match_outfitrecommendation'


class MixAndMatchOutfitrecommendationRecommendedItems(models.Model):
    id = models.BigAutoField(primary_key=True)
    outfitrecommendation = models.ForeignKey(MixAndMatchOutfitrecommendation, models.DO_NOTHING)
    product = models.ForeignKey(MarketplaceProduct, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'mix_and_match_outfitrecommendation_recommended_items'
        unique_together = (('outfitrecommendation', 'product'),)


class MixAndMatchUseroutfit(models.Model):
    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField()
    preview_image = models.CharField(max_length=100, blank=True, null=True)
    user = models.ForeignKey('UserCustomuser', models.DO_NOTHING)
    updated_at = models.DateTimeField()
    is_public = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'mix_and_match_useroutfit'


class OrdersOrder(models.Model):
    id = models.UUIDField(primary_key=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20)
    payment_method = models.CharField(max_length=10, blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    xendit_payment_request_id = models.CharField(unique=True, max_length=255, blank=True, null=True)
    xendit_payment_id = models.CharField(unique=True, max_length=255, blank=True, null=True)
    buyer = models.ForeignKey('UserCustomuser', models.DO_NOTHING, blank=True, null=True)
    country = models.CharField(max_length=2)
    currency = models.CharField(max_length=3)
    failure_reason = models.CharField(max_length=255, blank=True, null=True)
    payment_channel = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'orders_order'


class OrdersOrderitem(models.Model):
    id = models.BigAutoField(primary_key=True)
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    order = models.ForeignKey(OrdersOrder, models.DO_NOTHING)
    product = models.ForeignKey(MarketplaceProduct, models.DO_NOTHING, blank=True, null=True)
    seller = models.ForeignKey('UserCustomuser', models.DO_NOTHING, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'orders_orderitem'


class UserCustomuser(models.Model):
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(blank=True, null=True)
    is_superuser = models.BooleanField()
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    date_joined = models.DateTimeField()
    id = models.UUIDField(primary_key=True)
    email = models.CharField(unique=True, max_length=254)
    username = models.CharField(unique=True, max_length=255)
    is_active = models.BooleanField()
    is_staff = models.BooleanField()
    date_created = models.DateTimeField()
    is_email_verified = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'user_customuser'


class UserCustomuserGroups(models.Model):
    id = models.BigAutoField(primary_key=True)
    customuser = models.ForeignKey(UserCustomuser, models.DO_NOTHING)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'user_customuser_groups'
        unique_together = (('customuser', 'group'),)


class UserCustomuserUserPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    customuser = models.ForeignKey(UserCustomuser, models.DO_NOTHING)
    permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'user_customuser_user_permissions'
        unique_together = (('customuser', 'permission'),)


class UserUserprofile(models.Model):
    id = models.BigAutoField(primary_key=True)
    first_name = models.CharField(max_length=255, blank=True, null=True)
    last_name = models.CharField(max_length=255, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    profile_picture = models.CharField(max_length=100, blank=True, null=True)
    contact_number = models.CharField(max_length=15, blank=True, null=True)
    location = models.CharField(max_length=255, blank=True, null=True)
    user = models.OneToOneField(UserCustomuser, models.DO_NOTHING)
    appearance_prompt_notes = models.TextField(blank=True, null=True)
    body_type_ai = models.CharField(max_length=100, blank=True, null=True)
    ethnicity_ai = models.CharField(max_length=100, blank=True, null=True)
    height_cm = models.IntegerField(blank=True, null=True)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=1, blank=True, null=True)
    gender = models.CharField(max_length=20)
    age = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'user_userprofile'


class WalletWallet(models.Model):
    id = models.BigAutoField(primary_key=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    user = models.OneToOneField(UserCustomuser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'wallet_wallet'


class WalletWallettransaction(models.Model):
    id = models.UUIDField(primary_key=True)
    transaction_type = models.CharField(max_length=20)
    status = models.CharField(max_length=15)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    external_reference = models.CharField(max_length=255, blank=True, null=True)
    related_order_id = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField()
    wallet = models.ForeignKey(WalletWallet, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'wallet_wallettransaction'
