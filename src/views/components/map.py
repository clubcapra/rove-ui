from src.controller.event_bus import EventBus 
class map:

    def __init__(self, *args, **kwargs):
        self.eventBus = EventBus()
        self.eventBus.publish("log", "Map component initialized.")
        self.eventBus.subscribe("path_update", self.refresh)
        self.pathDatas = []  # Placeholder for path data structure
        pass

    def render(self):
        print("Rendering map component.")

    def refresh(self, pathDatas):
        """Update the map with new data."""
        print("Refreshing map with new data.")
        self.pathDatas.extend(pathDatas) 

        #TODO: Implement logic to update the map with new path data
