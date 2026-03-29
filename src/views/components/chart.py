class chart:
    """A simple chart component for displaying data visually."""

    def __init__(self, title, data):
        self.title = title
        self.data = data
        

    def render(self):
        # Placeholder for rendering logic
        print(f"Rendering chart: {self.title}")
        for key, value in self.data.items():
            print(f"{key}: {value}")

    def refresh(self, new_data):
        """Update the chart with new data."""
        self.data = new_data
        self.render()
        
