from dotenv import load_dotenv
import collections
import os
import websockets
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import serialization, hashes
import asyncio
import json
import sys
import pyqtgraph as pg
import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6 import QtWidgets
from PyQt6.QtCore import QTimer
from qasync import QEventLoop 
import traceback
import logging

"""
Connection lifecycle:
1. Initial Connection: Establish WebSocket with authentication headers
2. Subscribe: Send subscription commands for desired channels
3. Receive Updates: Process incoming messages based on their type
4. Handle Disconnects: Implement reconnection logic with exponential backoff
"""
"""
If you have a paper account, you can call:
    Trading API endpoints on paper-api.alpaca.markets
    Market Data API endpoints on data.alpaca.markets
"""


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

WSS_URL = "wss://stream.data.alpaca.markets/v2/test"
CRYPTO_WS_URL = f"wss://stream.data.alpaca.markets/v1beta3/crypto/us"
CRYPTO_DATA = collections.defaultdict(list)
TICKER = "BTC/USD"
VISIBLE_POINTS = 100          # how many points to show
Y_PADDING_PCT = 0.02          # 2% vertical padding
MIN_Y_RANGE_PCT = 0.002       # 0.2% minimum height

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        pg.setConfigOptions(antialias=True)

        self.plot_graph = pg.PlotWidget()
        self.setCentralWidget(self.plot_graph)

        self.plot_graph.setBackground("#0f172a")  # dark navy
        self.plot_graph.showGrid(x=True, y=True, alpha=0.25)

        self.plot_graph.getPlotItem().hideAxis("top")
        self.plot_graph.getPlotItem().hideAxis("right")

        self.plot_graph.setTitle(
            "BTC Price — Real Time",
            color="#38bdf8",
            size="18pt"
        )

        self.plot_graph.setXRange(0, 50)
        label_style = {"color": "#cbd5e1", "font-size": "14px"}
        self.plot_graph.setLabel("left", "Price ($)", **label_style)
        self.plot_graph.setLabel("bottom", "Time", **label_style)

    
        self.last_point_added = 0
        self.x, self.y = [], []
        # Price line pen
        pen = pg.mkPen(color="#22c55e", width=2)
        # Gradient fill below line
        brush = pg.mkBrush(34, 197, 94, 80)
        self.data_line = self.plot_graph.plot(
            self.x,
            self.y,
            pen=pen,
            fillLevel=0,
            brush=brush,
            symbol='o',                # circle
            symbolSize=10,              # circle size
            symbolBrush='#22c55e',     
            symbolPen=pg.mkPen('#16a34a', width=1)
        )
        self.plot_graph.enableAutoRange(x=True)
        # ----- TIMER -----
        self.timer = QTimer()
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.update_plot)
        self.timer.start()

    def update_plot(self):
        start_len = len(self.x)
        for i in range(self.last_point_added, len(CRYPTO_DATA[TICKER])):
            bar = CRYPTO_DATA[TICKER][i]
            self.last_point_added += 1

            price = float(bar["close"])
            self.x.append(len(self.x))
            self.y.append(price)

        if len(self.x) == start_len:
            return

        x_visible = self.x[-VISIBLE_POINTS:]
        y_visible = self.y[-VISIBLE_POINTS:]

        y_min = min(y_visible)
        y_max = max(y_visible)
        y_mid = (y_min + y_max) / 2

        y_range = y_max - y_min
        min_range = y_mid * MIN_Y_RANGE_PCT

        if y_range < min_range:
            y_range = min_range
            y_min = y_mid - y_range / 2
            y_max = y_mid + y_range / 2

        padding = y_range * Y_PADDING_PCT
        y_min -= padding
        y_max += padding

        self.plot_graph.setXRange(x_visible[0], x_visible[-1], padding=0)
        self.plot_graph.setYRange(y_min, y_max, padding=0)
        self.data_line.setData(x_visible, y_visible)
        logging.info(f"Plot updated | Y range: {y_min:.2f} - {y_max:.2f}")
      
async def subscribe_to_bar(ws):
    ticker = [TICKER]
    await ws.send(json.dumps(
        {"action": "subscribe", "bars": ticker}
    ))
    logging.info(f'Subscribed to bars channel for ticker: {ticker}')

async def handle_messages(ws):
    BAR_MSG_TYPE = "b"
    async for batch in ws:
        for data in json.loads(batch): 
            if data["T"] == BAR_MSG_TYPE:
                ticker = data["S"]
                CRYPTO_DATA[ticker].append({            
                    "open": data["o"],
                    "high": data["h"],
                    "low": data["l"],
                    "close": data["c"],
                })
                logging.info(f'Incoming data: {CRYPTO_DATA[ticker][-1]}')
                
async def auth(ws):
    await ws.send(json.dumps({
        "action": "auth",
          "key": f"{os.getenv("ALPACA_API_KEY")}", "secret": f"{os.getenv("ALPACA_SECRET")}",
    }))
    logging.info(f"Authorized self to WS {CRYPTO_WS_URL} connection")

async def main(rtplot):
    asyncio.create_task(start_websocket_stream())
    shut_down_event = asyncio.Event()
    rtplot.aboutToQuit.connect(shut_down_event.set)
    plot = MainWindow()
    plot.show()
    await shut_down_event.wait()
    logging.info("Exiting program plotting window is closed")

async def start_websocket_stream():
    logging.info(f"Attempting to connect to f{CRYPTO_WS_URL}")
    try: 
        async with websockets.connect(CRYPTO_WS_URL) as ws: 
            logging.info(f"Connected to {CRYPTO_WS_URL}") 
            await auth(ws)
            await asyncio.gather(
                subscribe_to_bar(ws),
                handle_messages(ws)
            )
    except: 
        traceback.print_exc()

if __name__ == "__main__":
    load_dotenv()
    app = QApplication(sys.argv)
    asyncio.run(main(app), loop_factory=QEventLoop)