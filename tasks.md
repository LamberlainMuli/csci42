Okay, let's break down the required fixes and features into a manageable task list. This will help us tackle the project step-by-step.

We'll focus on fixing the existing issues first, then move on to the new chat feature.

**Phase 1: Core Payment & Order Processing Fixes**

* **Task 1: Debug Xendit Payment Request Creation (`payments/services.py`)**
    * **Goal:** Ensure the payment request is being created correctly for all payment methods and that the necessary details (like `payment_channel`) are being captured or determined.
    * **Action:** Add detailed logging within `create_xendit_payment_request` to inspect the `selected_channel_key`, the derived `payment_type_str` and `channel_code_str`, and the final `payment_request_payload` just before the API call. Verify the API response structure.
    * **Check:** Confirm if the `Order` model's `payment_channel` field is being saved *after* a successful payment request initiation (it currently isn't in the service function, might need adjustment).

* **Task 2: Verify and Debug Xendit Webhook (`payments/views.py`)**
    * **Goal:** Ensure the webhook endpoint receives events from Xendit, verifies them correctly, and processes successful payments accurately. This is likely the *key area* for fixing stock/sold status issues.
    * **Action:**
        * Confirm the webhook URL is correctly configured in your Xendit dashboard.
        * Confirm `XENDIT_CALLBACK_VERIFICATION_TOKEN` is correctly set in `settings.py` and matches the token in Xendit.
        * Add *extensive* logging inside `xendit_webhook`: Log the raw request body, headers (especially `x-callback-token`), the parsed payload, the extracted `order_id`, the result of the `Order.objects.get`, and critical points *inside* the `transaction.atomic()` block (before/after status update, before/during/after stock update, before/after distribution).
        * Specifically check if the `payment.succeeded` (or equivalent) event is being received for successful payments.
        * Check server logs for any errors occurring during webhook processing (database errors, exceptions in `distribute_payment`, etc.).

* **Task 3: Fix Stock Deduction Logic (`payments/views.py`)**
    * **Goal:** Ensure product quantity is correctly decreased upon successful payment confirmation via the webhook.
    * **Action:** Review the stock deduction section within the `transaction.atomic()` block in `xendit_webhook`. The `Product.objects.filter(id=prod.id, quantity__gte=item.quantity).update(quantity=models.F('quantity') - item.quantity)` logic looks correct, but verify:
        * Is the `OrderItem` correctly linking to the `Product`?
        * Is `item.quantity` the correct value?
        * Are there any race conditions or errors preventing the update? (Logs from Task 2 are crucial here).

* **Task 4: Fix `is_sold` Status Update (`payments/views.py`)**
    * **Goal:** Ensure products are marked as sold (`is_sold = True`) when their quantity reaches zero after a successful sale via the webhook.
    * **Action:** Review the logic *after* the stock deduction in `xendit_webhook`:
        * `prod.refresh_from_db(fields=['quantity', 'is_sold'])`
        * `if prod.quantity <= 0 and not prod.is_sold:`
        * `prod.is_sold = True`
        * `prod.save(update_fields=['is_sold'])`
        * Verify this logic is being reached and executed correctly (check logs from Task 2).

* **Task 5: Ensure Order Fields are Populated (`payments/services.py` & `payments/views.py`)**
    * **Goal:** Make sure `Order.payment_channel` and `Order.xendit_payment_id` are correctly saved.
    * **Action:**
        * In `create_xendit_payment_request`: Store the determined `channel_code_str` or `payment_type_str` in `order.payment_channel` *before* making the API call or immediately after if the response confirms the channel. Save the order.
        * In `xendit_webhook`: Ensure `order_locked.xendit_payment_id = xendit_payment_id` is correctly saving the ID from the webhook payload for successful events.

**Phase 2: Dashboard Correction**

* **Task 6: Refactor Dashboard Data Source (`dashboard/views.py`)**
    * **Goal:** Display transaction/order information based on your *local* `Order` model data, not directly from the Xendit API, and potentially filter for specific users (e.g., seller's sales or admin view).
    * **Action:**
        * Remove the `Workspace_transactions` function that calls the Xendit API directly.
        * Modify `dashboard_view` to query the local `Order` model. Decide on the filtering logic:
            * *Admin View:* Fetch all `Order` objects.
            * *Seller View:* Fetch `Order` objects where `OrderItem.seller` is the logged-in user (requires joining Order and OrderItem).
        * Pass the queryset of `Order` objects to the template.

* **Task 7: Update Dashboard Template (`dashboard/templates/dashboard/dashboard.html`)**
    * **Goal:** Display the correct data (`Payment Channel`, `Created At`, `Status`, `Amount`, etc.) from the `Order` objects passed by the view.
    * **Action:** Modify the HTML template loop:
        * Iterate through the `Order` objects provided in the context (e.g., `{% for order in orders %}`).
        * Display relevant fields like `order.id`, `order.buyer.email` (or name), `order.created_at|date:"Y-m-d H:i"`, `order.get_status_display`, `order.total_amount`, `order.payment_channel`.
        * Remove references to the old `transactions` structure coming directly from the Xendit API.

**Phase 3: Seller Experience**

* **Task 8: Implement Seller Sale Notification**
    * **Goal:** Notify a seller when one of their items has been successfully purchased and paid for.
    * **Action:**
        * Decide on the notification method (e.g., Email, In-app notification model). Email is simpler initially.
        * In the `xendit_webhook`'s successful payment block (`transaction.atomic`), after stock deduction and status update:
            * Iterate through the `order_items`.
            * For each item, get the `item.seller`.
            * Send an email (using Django's `send_mail`) to `item.seller.email` containing order details (Order ID, Product sold, Quantity, Price, Buyer info if desired).
            * Handle potential multiple items from the same seller in one order efficiently (collect items per seller, then send one notification).

**Phase 4: New Feature - Chat System**

* **Task 9: Design Chat Models (`chat/models.py` - New App)**
    * **Goal:** Create database models to store chat conversations and messages.
    * **Action:**
        * Create a new Django app (e.g., `python manage.py startapp chat`).
        * Define models:
            * `Conversation`: Links participants (e.g., `buyer = ForeignKey(User)`, `seller = ForeignKey(User)`), potentially related to a `Product` or `Order`. Track timestamps.
            * `Message`: `ForeignKey` to `Conversation`, `sender = ForeignKey(User)`, `content = TextField`, `timestamp = DateTimeField(auto_now_add=True)`.

* **Task 10: Implement Basic Chat Views & URLs (`chat/views.py`, `chat/urls.py`)**
    * **Goal:** Create views to list conversations, view a specific conversation, and send messages.
    * **Action:**
        * `conversation_list_view`: Show conversations the logged-in user is part of.
        * `conversation_detail_view`: Display messages for a specific conversation. Include a form to send a new message.
        * `send_message_view` (or handle in detail view): Process the message form submission, create a `Message` object, save it, and redirect back to the detail view.
        * Define corresponding URL patterns.

* **Task 11: Create Chat Templates (`chat/templates/chat/`)**
    * **Goal:** Build HTML templates for listing conversations and viewing/interacting with a single conversation.
    * **Action:**
        * `conversation_list.html`: Loop through conversations, link to detail view.
        * `conversation_detail.html`: Display messages (sender, content, time), show the message input form.

* **Task 12: Integrate Chat Links**
    * **Goal:** Provide entry points for users to start chats.
    * **Action:** Add "Contact Seller" buttons on product detail pages and potentially "Contact Buyer" buttons on order detail pages (for sellers). These buttons should link to a view that finds or creates a `Conversation` and redirects to the `conversation_detail_view`.

**Phase 5: Testing and Refinement**

* **Task 13: Write Unit/Integration Tests**
    * **Goal:** Ensure core logic (especially payments, webhooks, stock updates) works reliably and prevent regressions.
    * **Action:** Create test cases in `payments/tests.py`, `orders/tests.py`, `marketplace/tests.py`, `dashboard/tests.py`, and `chat/tests.py`. Mock external services like the Xendit API where necessary. Test edge cases (insufficient stock, invalid webhook signatures, etc.).

* **Task 14: Review and Enhance Logging**
    * **Goal:** Improve logging across the application for easier debugging in the future.
    * **Action:** Review existing logging and add more informative logs where needed, particularly around critical workflows like payment processing and order updates. Configure Django logging settings appropriately.

* **Task 15: Security Review**
    * **Goal:** Double-check security aspects.
    * **Action:** Ensure webhook verification is robust, CSRF protection is used correctly, user permissions are checked (e.g., only sellers can edit their products), and sensitive keys are not exposed.

Let's start with **Task 1: Debug Xendit Payment Request Creation (`payments/services.py`)**. Please provide the current version of `payments/services.py` again if it has changed, or confirm if the version in the initial prompt is the one we should work with. We'll add logging to see what's happening during payment initiation.