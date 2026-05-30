import pyvista as pv
import numpy as np
import time

def main():
    print("Initializing Native 3D JARVIS Core Viewer...")
    
    # Create the Plotter window
    plotter = pv.Plotter(title="JARVIS 2.0 - Native 3D Core", window_size=[800, 600])
    plotter.set_background("#020617")  # Deep slate/dark background
    
    # Create geometric shapes for the holographic core
    # 1. Outer wireframe shell
    outer_sphere = pv.Sphere(radius=1.2, theta_resolution=30, phi_resolution=30)
    # 2. Inner core sphere
    inner_sphere = pv.Sphere(radius=0.7, theta_resolution=20, phi_resolution=20)
    # 3. Middle orbiting rings
    ring_geom = pv.Torus(inner_radius=0.9, outer_radius=0.95)
    
    # Add meshes to the plotter
    outer_actor = plotter.add_mesh(
        outer_sphere, 
        color="#38bdf8", 
        style="wireframe", 
        line_width=1, 
        opacity=0.3,
        name="outer_shell"
    )
    
    inner_actor = plotter.add_mesh(
        inner_sphere, 
        color="#0284c7", 
        style="surface", 
        opacity=0.8,
        lighting=True,
        specular=1.0,
        specular_power=10,
        name="inner_core"
    )
    
    ring_actor = plotter.add_mesh(
        ring_geom,
        color="#f43f5e", # Glowing red ring
        style="wireframe",
        opacity=0.6,
        name="orbiting_ring"
    )
    
    # Add text overlay
    plotter.add_text(
        "JARVIS 2.0 - NATIVE 3D CORE ACTIVE\nNO JS | NO BROWSER | GPU ACCELERATED",
        position="upper_left",
        font_size=10,
        color="#38bdf8",
        font="courier"
    )
    
    # Add visual bounds/grid for a sci-fi look
    plotter.add_axes()
    
    print("\nStarting the rendering loop. Close the window to exit.")
    
    # Show the window and start interactive loop
    plotter.show(interactive_update=True)
    
    # Rotate the components in real-time
    angle = 0
    while plotter.render():
        # Rotate outer shell clockwise
        outer_actor.RotateY(0.5)
        outer_actor.RotateX(0.2)
        
        # Rotate inner core counter-clockwise
        inner_actor.RotateZ(-0.3)
        
        # Spin the ring on a different axis
        ring_actor.RotateZ(1.2)
        ring_actor.RotateY(0.4)
        
        # Pulse the inner core's opacity to look like a breathing heartbeat
        opacity = 0.5 + 0.3 * np.sin(time.time() * 3)
        inner_actor.GetProperty().SetOpacity(opacity)
        
        time.sleep(0.01)
        plotter.update()

if __name__ == "__main__":
    main()
