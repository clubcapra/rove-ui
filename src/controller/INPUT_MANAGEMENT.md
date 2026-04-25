# Gestion des Inputs Manette

## Vue d'ensemble

Les messages Joy reçus via ROS2 sont distribués individuellement via l'EventBus pour que seuls les composants UI qui écoutent les inputs spécifiques soient notifiés.

## Architecture

### 1. Réception des messages Joy (ROS2Client)

- Le `ROS2Client` reçoit les messages `sensor_msgs/msg/Joy` du topic `/joy`
- Le transformateur `_transform_joy` convertit le message en événements individuels

### 2. Distribution des événements

Avec la configuration par défaut (`event_topic: "input"`), les événements publiés sont:

```
input                    # Message Joy complet (payload dict)
input.button.0          # Bouton 0 (0 ou 1)
input.button.1          # Bouton 1
...
input.button.23         # Bouton 23
input.axis.0            # Axe 0 (valeur float -1.0 à 1.0)
input.axis.1            # Axe 1
...
input.axis.11           # Axe 11
```

### 3. Utilisation dans les composants UI

#### Exemple: Écouter un bouton spécifique

```python
from src.controller.event_bus import EventBus

class MyGamepadController(QWidget):
    def __init__(self):
        super().__init__()
        self.event_bus = EventBus()
        
        # Écouter le bouton A (button index 0)
        self.event_bus.subscribe("input.button.0", self.on_button_a_pressed)
        
        # Écouter le stick gauche X (axis index 0)
        self.event_bus.subscribe("input.axis.0", self.on_stick_left_x)
    
    def on_button_a_pressed(self, value: int):
        if value == 1:
            print("Bouton A pressé")
        else:
            print("Bouton A relâché")
    
    def on_stick_left_x(self, value: float):
        print(f"Stick gauche X: {value:.2f}")
```

## Référence des inputs

### Mapping XBOX Controller Bluetooth

#### Boutons (indexes dans le message Joy)

| Index | Bouton | Code evdev |
|-------|--------|-----------|
| 0 | A | 304 |
| 1 | B | 305 |
| 2 | X | 307 |
| 3 | Y | 308 |
| 4 | LB | 310 |
| 5 | RB | 311 |
| 6 | VIEW (Select) | 314 |
| 7 | MENU (Start) | 315 |
| 8 | SUPER (Home) | 316 |
| 9 | LS_BTN (Stick gauche) | 317 |
| 10 | RS_BTN (Stick droit) | 318 |
| 11 | SHARE (F12) | 167 |
| 12 | DPAD_UP | - |
| 13 | DPAD_DOWN | - |
| 14 | DPAD_LEFT | - |
| 15 | DPAD_RIGHT | - |
| 16 | LT_BTN | - |
| 17 | RT_BTN | - |

#### Axes (indexes dans le message Joy)

| Index | Axe | Plage | Signification |
|-------|-----|-------|---------------|
| 0 | LS_X | [-1, 1] | Stick gauche horizontal |
| 1 | LS_Y | [-1, 1] | Stick gauche vertical |
| 2 | LT | [-1, 1] | Gâchette gauche (0 relâchée → 1 enfoncée) |
| 3 | RS_X | [-1, 1] | Stick droit horizontal |
| 4 | RS_Y | [-1, 1] | Stick droit vertical |
| 5 | RT | [-1, 1] | Gâchette droite (0 relâchée → 1 enfoncée) |
| 6 | D_PAD_X | [-1, 0, 1] | D-PAD horizontal |
| 7 | D_PAD_Y | [-1, 0, 1] | D-PAD vertical |

## Configuration

### Ajouter un nouveau topic Joy

Modifiez `config/config_window1.json` pour ajouter ou modifier le topic Joy:

```json
{
  "name": "/joy",
  "msg_type": "sensor_msgs/msg/Joy",
  "qos_depth": 10,
  "event_topic": "input",
  "transform": "joy"
}
```

- `name`: Topic ROS2 (`/joy` par défaut)
- `event_topic`: Préfixe pour les événements publiés (`input` par défaut)
- `transform`: Type de transformation (`joy` pour les messages Joy)

### Utilisation avancée avec InputManager

Pour des applications complexes avec plusieurs manettes et mappings sémantiques, utilisez `InputManager`:

```python
from src.controller.input_manager import InputManager
from src.controller.event_bus import EventBus

# Initialiser
manager = InputManager(EventBus())

# Charger la configuration d'une manette
device_config = {
    "name": "XBOX Controller (Bluetooth)",
    "udev_path": "/dev/input/xbox_bl_controller_laptop",
    "id": "045e:028e",
    "alias": "xbox_bluetooth",
    "enabled": True,
    "deadzone": 0.05,
    "mapping": {
        "buttons": {0: 304, 1: 305, ...},
        "axes": {0: 0, 1: 1, ...},
        "axis_ranges": {2: [0, 1023], 5: [0, 1023], ...},
        "axes_as_buttons": [
            {"axis_code": 17, "neg_button": 12, "pos_button": 13, "threshold": 0.5},
            ...
        ]
    }
}

manager.set_device_mapping(device_config)

# Traiter les messages Joy
manager.process_joy_message(
    device_alias="xbox_bluetooth",
    axes=[0.0, 0.5, 1.0, ...],  # Du message Joy
    buttons=[0, 0, 1, ...]        # Du message Joy
)
```

#### Événements publiés par InputManager

```
input.{device_alias}.button.{code}        # État du bouton (0/1)
input.{device_alias}.axis.{code}          # Valeur de l'axe (-1 à 1, avec deadzone appliquée)
input.{device_alias}.pressed.{code}       # Événement de pression
input.{device_alias}.released.{code}      # Événement de relâchement
```

## Débugage

Les événements publiés sont loggés automatiquement via l'EventBus. Consultez la console de debug pour voir:

```
Event published: input with args: (...)
Event published: input.button.0 with args: (1,)
Event published: input.axis.0 with args: (0.45,)
```

## Deadzone

Le deadzone par défaut est de 0.05 (-1 à 1). Les valeurs d'axe en dessous du deadzone sont converties en 0.0 pour éviter la dérive.

Modifiez dans `config_window1.json` (via InputManager) ou directement dans le code.

## Notes

- Les outputs/vibrations ne sont pas actuellement supportées
- Le multi-manette est supporté en configure plusieurs topics Joy ou en utilisant InputManager
- Les axes avec normalization custom (like D-PAD ou triggers) doivent être configurées dans `axis_ranges`
