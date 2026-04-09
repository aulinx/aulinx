import pyatspi

desktop = pyatspi.Registry.getDesktop(0)
print("Apps:", desktop.childCount)
for app in desktop:
    print(" ", app.name, "(" + str(app.childCount) + " children)")
    for win in app:
        print("   ", win.name, "role=" + win.getRoleName())
