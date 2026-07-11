import logging
import os
import uuid
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ═══════════════════════════════════════════════════
# الإعدادات (من Environment Variables)
# ═══════════════════════════════════════════════════

BOT_TOKEN = os.environ.get("BOT_TOKEN", "ضع_توكن_البوت_هنا")
API_TOKEN = os.environ.get("API_TOKEN", "ضع_api_token_هنا")
BASE_URL = "https://api.oranosmarket.com"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════
# دوال API
# ═══════════════════════════════════════════════════

def api_get(endpoint, params=None):
    headers = {"api-token": API_TOKEN}
    try:
        response = requests.get(f"{BASE_URL}{endpoint}", headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"API Error: {e}")
        return None

def api_post(endpoint, params=None):
    headers = {"api-token": API_TOKEN}
    try:
        response = requests.get(f"{BASE_URL}{endpoint}", headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"API Error: {e}")
        return None

# ═══════════════════════════════════════════════════
# حالات المحادثة
# ═══════════════════════════════════════════════════
(SELECTING_CATEGORY, SELECTING_PRODUCT, ENTERING_QTY, ENTERING_PARAMS, CONFIRM_ORDER) = range(5)

# ═══════════════════════════════════════════════════
# أوامر البوت
# ═══════════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    profile = api_get("/client/api/profile")
    balance = profile.get("balance", "0.00") if profile else "0.00"
    
    welcome_text = (
        f"👋 أهلاً يا <b>{user.first_name}</b>!\n\n"
        f"🎮 <b>بوت Oranos Market</b>\n"
        f"💰 <b>رصيدك:</b> <code>{balance}$</code>\n\n"
        f"📌 اختر من القائمة:"
    )
    
    keyboard = [
        ["🎮 الألعاب", "📱 شحن الرصيد"],
        ["💬 تطبيقات الدردشة", "📦 كل المنتجات"],
        ["👤 حسابي", "📋 طلباتي"],
    ]
    
    await update.message.reply_text(
        welcome_text,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "📖 <b>كيفية الاستخدام:</b>\n\n"
        "1️⃣ اضغط على القسم اللي بدك إياه\n"
        "2️⃣ اختار المنتج المناسب\n"
        "3️⃣ أدخل الكمية المطلوبة\n"
        "4️⃣ أدخل البيانات المطلوبة (مثل ID اللاعب)\n"
        "5️⃣ أكد الطلب\n\n"
        "⚠️ تأكد من صحة ID اللاعب قبل الطلب"
    )
    await update.message.reply_text(help_text, parse_mode="HTML")

async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    profile = api_get("/client/api/profile")
    if not profile:
        await update.message.reply_text("❌ تعذر الاتصال بالخادم.")
        return
    
    balance = profile.get("balance", "0.00")
    email = profile.get("email", "غير متوفر")
    
    text = (
        "👤 <b>حسابك</b>\n\n"
        f"📧 <b>البريد:</b> {email}\n"
        f"💰 <b>الرصيد:</b> <code>{balance}$</code>\n\n"
        f"🔄 <b>للشحن:</b> تواصل مع @support"
    )
    await update.message.reply_text(text, parse_mode="HTML")

# ═══════════════════════════════════════════════════
# عرض المنتجات
# ═══════════════════════════════════════════════════

async def show_all_products(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    products = api_get("/client/api/products")
    
    if not products or not isinstance(products, list):
        await update.message.reply_text("❌ تعذر جلب المنتجات.")
        return ConversationHandler.END
    
    context.user_data["products_list"] = products
    
    keyboard = []
    for prod in products[:15]:
        name = prod.get("name", "منتج")
        price = prod.get("price", 0)
        pid = prod.get("id", 0)
        keyboard.append([InlineKeyboardButton(f"🛒 {name} ({price}$)", callback_data=f"prod_{pid}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    
    await update.message.reply_text(
        "📦 <b>اختر منتج:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECTING_PRODUCT

async def product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    prod_id = int(query.data.replace("prod_", ""))
    products = api_get(f"/client/api/products?products_id={prod_id}")
    
    if not products or not isinstance(products, list) or len(products) == 0:
        await query.edit_message_text("❌ المنتج غير متوفر.")
        return ConversationHandler.END
    
    product = products[0]
    context.user_data["selected_product"] = product
    
    name = product.get("name", "منتج")
    price = product.get("price", 0)
    params = product.get("params", [])
    qty_info = product.get("qty_values", {})
    
    qty_text = ""
    if qty_info is None:
        qty_text = "الكمية: 1 (ثابتة)"
        context.user_data["fixed_qty"] = True
    elif isinstance(qty_info, dict):
        min_qty = qty_info.get("min", 1)
        max_qty = qty_info.get("max", "غير محدد")
        qty_text = f"الكمية: من {min_qty} إلى {max_qty}"
        context.user_data["fixed_qty"] = False
        context.user_data["qty_min"] = int(min_qty) if str(min_qty).isdigit() else 1
        context.user_data["qty_max"] = int(max_qty) if str(max_qty).isdigit() else 999999
    
    text = f"🎮 <b>{name}</b>\n💰 السعر: <code>{price}$</code>\n📊 {qty_text}\n\n"
    
    if params:
        text += "📝 <b>المعلومات المطلوبة:</b>\n"
        for p in params:
            text += f"  • {p}\n"
        context.user_data["required_params"] = params
    else:
        context.user_data["required_params"] = []
    
    text += "\n💡 أرسل الكمية المطلوبة:"
    
    keyboard = [[InlineKeyboardButton("❌ إلغاء", callback_data="cancel_order")]]
    
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    return ENTERING_QTY

async def enter_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    
    try:
        qty = int(text)
    except ValueError:
        await update.message.reply_text("⚠️ يرجى إدخال رقم صحيح.")
        return ENTERING_QTY
    
    if context.user_data.get("fixed_qty"):
        qty = 1
    else:
        min_q = context.user_data.get("qty_min", 1)
        max_q = context.user_data.get("qty_max", 999999)
        if qty < min_q:
            await update.message.reply_text(f"⚠️ الحد الأدنى: {min_q}")
            return ENTERING_QTY
        if qty > max_q:
            await update.message.reply_text(f"⚠️ الحد الأقصى: {max_q}")
            return ENTERING_QTY
    
    context.user_data["quantity"] = qty
    params = context.user_data.get("required_params", [])
    
    if not params:
        return await confirm_order_direct(update, context)
    
    context.user_data["param_index"] = 0
    context.user_data["param_values"] = {}
    
    await update.message.reply_text(
        f"📝 <b>{params[0]}</b>\n\nأدخل القيمة:",
        parse_mode="HTML",
    )
    return ENTERING_PARAMS

async def enter_params(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = update.message.text.strip()
    params = context.user_data.get("required_params", [])
    idx = context.user_data.get("param_index", 0)
    
    param_name = params[idx]
    context.user_data["param_values"][param_name] = value
    
    if idx + 1 < len(params):
        context.user_data["param_index"] = idx + 1
        await update.message.reply_text(
            f"📝 <b>{params[idx + 1]}</b>\n\nأدخل القيمة:",
            parse_mode="HTML",
        )
        return ENTERING_PARAMS
    
    return await confirm_order_direct(update, context)

async def confirm_order_direct(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    product = context.user_data["selected_product"]
    qty = context.user_data.get("quantity", 1)
    param_values = context.user_data.get("param_values", {})
    
    name = product.get("name", "منتج")
    price = float(product.get("price", 0))
    total = price * qty
    
    text = (
        f"📋 <b>ملخص الطلب:</b>\n\n"
        f"🎮 المنتج: {name}\n"
        f"📊 الكمية: {qty}\n"
        f"💰 السعر للوحدة: {price}$\n"
        f"💵 <b>الإجمالي: {total:.2f}$</b>\n\n"
    )
    
    if param_values:
        text += "📝 <b>البيانات:</b>\n"
        for k, v in param_values.items():
            text += f"  • {k}: <code>{v}</code>\n"
    
    text += "\n✅ هل تؤكد الطلب؟"
    
    keyboard = [
        [
            InlineKeyboardButton("✅ تأكيد", callback_data="confirm_yes"),
            InlineKeyboardButton("❌ إلغاء", callback_data="confirm_no"),
        ]
    ]
    
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM_ORDER

async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_no":
        await query.edit_message_text("❌ تم إلغاء الطلب.")
        context.user_data.clear()
        return ConversationHandler.END
    
    product = context.user_data.get("selected_product")
    qty = context.user_data.get("quantity", 1)
    param_values = context.user_data.get("param_values", {})
    
    if not product:
        await query.edit_message_text("❌ خطأ: لا يوجد منتج مختار.")
        return ConversationHandler.END
    
    prod_id = product.get("id")
    order_uuid = str(uuid.uuid4())
    params_str = f"?qty={qty}&order_uuid={order_uuid}"
    
    for key, val in param_values.items():
        params_str += f"&{key}={val}"
    
    endpoint = f"/client/api/newOrder/{prod_id}/params{params_str}"
    result = api_post(endpoint)
    
    if not result:
        await query.edit_message_text("❌ فشل الاتصال بالخادم.")
        return ConversationHandler.END
    
    status = result.get("status", "ERROR")
    data = result.get("data", {})
    
    if status != "OK":
        error_msg = "❌ فشل الطلب"
        await query.edit_message_text(error_msg)
        return ConversationHandler.END
    
    order_id = data.get("order_id", "غير معروف")
    order_status = data.get("status", "غير معروف")
    final_price = data.get("price", 0)
    
    success_text = (
        f"✅ <b>تم تنفيذ الطلب!</b>\n\n"
        f"🆔 <b>رقم الطلب:</b> <code>{order_id}</code>\n"
        f"📊 <b>الحالة:</b> {order_status}\n"
        f"💰 <b>السعر:</b> {final_price}$\n\n"
        f"🔍 تابع عبر /orders"
    )
    
    await query.edit_message_text(success_text, parse_mode="HTML")
    context.user_data.clear()
    return ConversationHandler.END

async def check_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🔍 أرسل رقم الطلب للتحقق:\nمثال: <code>ID_xxxxxxxx</code>",
        parse_mode="HTML",
    )

async def check_order_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    order_id = update.message.text.strip()
    endpoint = f"/client/api/check?orders=[{order_id}]"
    result = api_get(endpoint)
    
    if not result or result.get("status") != "OK":
        await update.message.reply_text("❌ تعذر جلب معلومات الطلب.")
        return
    
    orders = result.get("data", [])
    if not orders:
        await update.message.reply_text("📭 لا يوجد طلب بهذا الرقم.")
        return
    
    order = orders[0]
    text = (
        f"📋 <b>تفاصيل الطلب:</b>\n\n"
        f"🆔 الرقم: <code>{order.get('order_id')}</code>\n"
        f"🎮 المنتج: {order.get('product_name')}\n"
        f"📊 الكمية: {order.get('quantity')}\n"
        f"💰 السعر: {order.get('price')}$\n"
        f"📊 الحالة: {order.get('status')}\n"
        f"📅 التاريخ: {order.get('created_at')}\n"
    )
    
    replay = order.get("replay_api", [])
    if replay and replay != [None]:
        text += f"\n📤 الرد: {replay}"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def handle_main_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    
    if text == "📦 كل المنتجات":
        return await show_all_products(update, context)
    elif text == "👤 حسابي":
        await my_account(update, context)
    elif text == "📋 طلباتي":
        await check_orders(update, context)
    elif text in ["🎮 الألعاب", "📱 شحن الرصيد", "💬 تطبيقات الدردشة"]:
        content = api_get("/client/api/content/0")
        if not content:
            await update.message.reply_text("❌ تعذر جلب الأقسام.")
            return
        
        keywords_map = {
            "🎮 الألعاب": ["pubg", "free fire", "uc", "game", "ببجي", "فري فاير"],
            "📱 شحن الرصيد": ["syriatel", "mtn", "رصيد", "شحن", "سيرياتيل"],
            "💬 تطبيقات الدردشة": ["telegram", "instagram", "tiktok", "youtube", "متابعين"],
        }
        
        keywords = keywords_map.get(text, [])
        keyboard = []
        
        for cat in content:
            name = cat.get("name", "").lower()
            if any(kw in name for kw in keywords):
                cat_id = cat.get("id", 0)
                keyboard.append([InlineKeyboardButton(f"📂 {cat.get('name')}", callback_data=f"cat_{cat_id}")])
        
        if not keyboard:
            keyboard.append([InlineKeyboardButton("📦 عرض كل المنتجات", callback_data="show_all")])
        
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
        
        await update.message.reply_text(
            f"{text} <b>الأقسام:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    cat_id = int(query.data.replace("cat_", ""))
    content = api_get(f"/client/api/content/{cat_id}")
    
    if not content:
        await query.edit_message_text("❌ القسم فارغ.")
        return ConversationHandler.END
    
    products = content if isinstance(content, list) else content.get("products", [])
    
    if not products:
        await query.edit_message_text("📭 لا توجد منتجات.")
        return ConversationHandler.END
    
    context.user_data["current_products"] = products
    
    keyboard = []
    for prod in products:
        name = prod.get("name", "منتج")
        price = prod.get("price", 0)
        pid = prod.get("id", 0)
        available = "✅" if prod.get("available", True) else "❌"
        keyboard.append([InlineKeyboardButton(f"{available} {name} — {price}$", callback_data=f"prod_{pid}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_cats")])
    
    await query.edit_message_text(
        "🛒 <b>اختر المنتج:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SELECTING_PRODUCT

async def general_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "back_main":
        await start(update, context)
    elif data == "back_cats":
        content = api_get("/client/api/content/0")
        if content:
            keyboard = []
            for cat in content:
                cat_id = cat.get("id", 0)
                keyboard.append([InlineKeyboardButton(f"📂 {cat.get('name')}", callback_data=f"cat_{cat_id}")])
            keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
            await query.edit_message_text("📂 <b>اختر القسم:</b>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data == "show_all":
        await show_all_products(update, context)
    elif data == "cancel_order":
        await query.edit_message_text("❌ تم إلغاء الطلب.")
        context.user_data.clear()

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Update {update} caused error {context.error}")

# ═══════════════════════════════════════════════════
# الدالة الرئيسية
# ═══════════════════════════════════════════════════

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    
    order_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^(🎮 الألعاب|📱 شحن الرصيد|💬 تطبيقات الدردشة|📦 كل المنتجات)$"), handle_main_buttons),
        ],
        states={
            SELECTING_CATEGORY: [CallbackQueryHandler(category_callback, pattern="^cat_")],
            SELECTING_PRODUCT: [CallbackQueryHandler(product_callback, pattern="^prod_")],
            ENTERING_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_quantity)],
            ENTERING_PARAMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_params)],
            CONFIRM_ORDER: [
                CallbackQueryHandler(confirm_callback, pattern="^confirm_"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", lambda u, c: u.message.reply_text("❌ تم الإلغاء.")),
        ],
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("account", my_account))
    application.add_handler(CommandHandler("orders", check_orders))
    application.add_handler(order_conv)
    application.add_handler(CallbackQueryHandler(general_callback, pattern="^(back_|show_|cancel_)"))
    application.add_handler(CallbackQueryHandler(category_callback, pattern="^cat_"))
    application.add_handler(CallbackQueryHandler(product_callback, pattern="^prod_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_order_by_id))
    application.add_error_handler(error_handler)
    
    logger.info("🚀 البوت يعمل الآن!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
