from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton



start_inline_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Мне нужно распечатать", callback_data="print")],
        [InlineKeyboardButton(text="Я печатаю", callback_data="printer")]
    ]
)

change_button = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Изменить данные", callback_data = "change")]
    ]
)

printer_type = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Лазерный ч/б", callback_data="printer_type_laser_bw")],
        [InlineKeyboardButton(text="Лазерный ч/б + цвет", callback_data="printer_type_laser_color")],
        [InlineKeyboardButton(text="Лазерный ч/б + скан", callback_data="printer_type_laser_bw_scan")],
        [InlineKeyboardButton(text="Лазерный ч/б + цвет + скан", callback_data="printer_type_laser_color_scan")],
        [InlineKeyboardButton(text="Струйный ч/б", callback_data="printer_type_ink_bw")],
        [InlineKeyboardButton(text="Струйный ч/б + цвет", callback_data="printer_type_ink_color")],
        [InlineKeyboardButton(text="Струйный ч/б + скан", callback_data="printer_type_ink_bw_scan")],
        [InlineKeyboardButton(text="Струйный ч/б + цвет + скан", callback_data="printer_type_ink_color_scan")],
    ]
)