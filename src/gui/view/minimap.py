import cv2
import tkinter as tk
from PIL import ImageTk, Image
from src.gui.interfaces import LabelFrame
from src.common import config, utils
from src.routine.components import Point


class Minimap(LabelFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, 'Minimap', **kwargs)

        self.WIDTH = 400
        self.HEIGHT = 300
        self.canvas = tk.Canvas(self, bg='black',
                                width=self.WIDTH, height=self.HEIGHT,
                                borderwidth=0, highlightthickness=0)
        self.canvas.pack(expand=True, fill='both', padx=5, pady=5)
        self.container = None
        # Reuse a single PhotoImage and update with paste() to avoid Tk/PIL memory leak
        # when repeatedly calling canvas.itemconfig(image=...) with new PhotoImages.
        self._photo = None

    def display_minimap(self):
        """Updates the Main page with the current minimap."""

        minimap = config.capture.minimap
        if not minimap:
            return

        rune_active = minimap['rune_active']
        rune_pos = minimap['rune_pos']
        path = minimap['path']
        player_pos = minimap['player_pos']

        img = cv2.cvtColor(minimap['minimap'], cv2.COLOR_BGR2RGB)
        height, width, _ = img.shape

        # Resize minimap to fit the Canvas
        ratio = min(self.WIDTH / width, self.HEIGHT / height)
        new_width = int(width * ratio)
        new_height = int(height * ratio)
        if new_height <= 0 or new_width <= 0:
            return
        img = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)

        # Mark the position of the active rune
        if rune_active:
            cv2.circle(img,
                       utils.convert_to_absolute(rune_pos, img),
                       3,
                       (128, 0, 128),
                       -1)

        # Draw the current path that the program is taking
        if config.enabled and len(path) > 1:
            for i in range(len(path) - 1):
                start = utils.convert_to_absolute(path[i], img)
                end = utils.convert_to_absolute(path[i + 1], img)
                cv2.line(img, start, end, (0, 255, 255), 1)

        # Draw each Point in the routine as a circle
        for p in config.routine.sequence:
            if isinstance(p, Point):
                utils.draw_location(img,
                                    p.location,
                                    (0, 255, 0) if config.enabled else (255, 0, 0))

        # Display the current Layout
        if config.layout:
            config.layout.draw(img)

        # Draw the player's position on top of everything
        cv2.circle(img,
                   utils.convert_to_absolute(player_pos, img),
                   3,
                   (0, 0, 255),
                   -1)

        # Reuse a single PhotoImage and update with paste() to avoid memory leak
        # from creating a new PhotoImage every frame (Tk/PIL leak on itemconfig).
        try:
            pil_img = Image.fromarray(img)
            # Create full-size black background and paste minimap centered (letterbox).
            # The PIL Image (~360KB) is small compared to frames, so recreating is fine.
            full = Image.new('RGB', (self.WIDTH, self.HEIGHT), (0, 0, 0))
            x = (self.WIDTH - new_width) // 2
            y = (self.HEIGHT - new_height) // 2
            full.paste(pil_img, (x, y))
            
            if self._photo is None:
                self._photo = ImageTk.PhotoImage(image=full)
                self.container = self.canvas.create_image(
                    self.WIDTH // 2, self.HEIGHT // 2, image=self._photo, anchor=tk.CENTER
                )
            else:
                self._photo.paste(full)
        except MemoryError:
            # If allocation fails, skip this frame update (next frame will retry).
            pass
