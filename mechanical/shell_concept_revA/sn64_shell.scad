// SN 64 cartridge shell concept Rev A
// Units: millimetres. Layout concept only; replace CONCEPT dimensions with measured values.
// OpenSCAD view_mode: 0 assembled, 1 exploded, 2 cutaway/keepouts.

$fn = 48;
view_mode = 0;
show_keepouts = (view_mode == 2);

// ---- Controlling envelope ----
L = 126;                 // X: long axis / cartridge width
W = 78;                  // Y: front-to-back width
H = 30;                  // Z: complete shell height
wall = 2.4;
split_z = 0;                  // shell mating plane, centered on the model

// ---- PCB and internal clearance ----
pcb_L = 111;
pcb_W = 57;
pcb_t = 1.6;
pcb_z = 11.0;
pcb_clear = 2.0;

// ---- Top female SNES connector / cartridge throat ----
snes_slot_L = 66;
snes_slot_W = 9;
snes_body_L = 72;
snes_body_W = 18;
snes_body_H = 14;
snes_slot_y = 0;

// ---- Bottom male N64 edge-card interface ----
n64_edge_L = 43;
n64_edge_W = 4.0;
n64_edge_drop = 10;
n64_slot_y = 0;

// ---- Side USB-C service opening ----
usbc_cut_W = 10;         // opening along Y on right side
usbc_cut_H = 5;
usbc_z = 15;
usbc_recess = 1.5;

// ---- Mounting bosses ----
boss_d = 7;
boss_h = 8;
boss_hole = 2.6;
boss_xy = [ [-(pcb_L/2-8), -(pcb_W/2-8)],
             [ (pcb_L/2-8), -(pcb_W/2-8)],
             [-(pcb_L/2-8),  (pcb_W/2-8)],
             [ (pcb_L/2-8),  (pcb_W/2-8)] ];

module rounded_box(size=[10,10,10], r=2, center=true) {
    // Minkowski gives a printable radius without relying on a particular OpenSCAD version.
    minkowski() {
        cube([size[0]-2*r, size[1]-2*r, size[2]-2*r], center=center);
        sphere(r=r);
    }
}

module shell_outer() {
    rounded_box([L,W,H], 4, true);
}

module inner_cavity() {
    // Slightly oversized through cavity; front/back wall remains structural.
    translate([0,0,0])
        rounded_box([L-2*wall, W-2*wall, H-2*wall+0.2], 2.4, true);
}

module top_snes_opening() {
    // Guided mouth for a vertical SNES/SFC cartridge. Connector body sits below this.
    translate([0,snes_slot_y,H/2+0.1])
        cube([snes_slot_L, snes_slot_W, 5], center=true);
    // Relief around the connector body, not a final vendor footprint.
    translate([0, snes_slot_y, H/2-5])
        cube([snes_body_L, snes_body_W, 10], center=true);
}

module bottom_n64_opening() {
    // Tongue exits the bottom and remains attached to the PCB; shell is not the contact carrier.
    translate([0,n64_slot_y,-H/2-0.1])
        cube([n64_edge_L, n64_edge_W, 6], center=true);
}

module side_usbc_opening() {
    // Right-side panel opening. Actual receptacle placement belongs to the PCB datum.
    translate([L/2+0.1,0,usbc_z-H/2])
        rotate([0,90,0])
            cube([usbc_cut_H, usbc_cut_W, 6], center=true);
    // shallow external finger/cable relief
    translate([L/2-usbc_recess/2,0,usbc_z-H/2])
        rotate([0,90,0])
            cube([usbc_cut_H+2, usbc_cut_W+4, usbc_recess+0.5], center=true);
}

module boss(x,y,z0,z1) {
    difference() {
        translate([x,y,(z0+z1)/2])
            cylinder(d=boss_d, h=z1-z0, center=true);
        translate([x,y,z0-0.1])
            cylinder(d=boss_hole, h=(z1-z0)+0.2, center=false);
    }
}

module bosses_for_half(z0,z1) {
    for (p = boss_xy) boss(p[0],p[1],z0,z1);
}

module upper_shell() {
    difference() {
        intersection() {
            shell_outer();
            translate([0,0,(split_z+H/2)/2])
                cube([L+2,W+2,H/2-split_z+0.01], center=true);
        }
        inner_cavity();
        top_snes_opening();
        side_usbc_opening();
        // screw/boss clearance slots at the split plane
        for (p = boss_xy)
            translate([p[0],p[1],split_z]) cylinder(d=boss_d+1.2,h=4,center=true);
    }
    // bosses hang down from the upper half toward the PCB datum
    bosses_for_half(split_z-0.2, split_z+boss_h);
}

module lower_shell() {
    difference() {
        intersection() {
            shell_outer();
            translate([0,0,(-H/2+split_z)/2])
                cube([L+2,W+2,H/2+split_z+0.01], center=true);
        }
        inner_cavity();
        bottom_n64_opening();
        side_usbc_opening();
        for (p = boss_xy)
            translate([p[0],p[1],split_z]) cylinder(d=boss_d+1.2,h=4,center=true);
    }
}

module pcb_keepout() {
    color([0.05,0.35,0.08,0.8])
        translate([0,0,pcb_z]) cube([pcb_L,pcb_W,pcb_t],center=true);
}

module snes_connector_keepout() {
    color([0.15,0.35,0.85,0.75])
        translate([0,snes_slot_y, H/2-snes_body_H/2-2])
            cube([snes_body_L,snes_body_W,snes_body_H],center=true);
}

module n64_edge_keepout() {
    color([0.85,0.65,0.08,0.9])
        translate([0,n64_slot_y,-H/2-n64_edge_drop/2])
            cube([n64_edge_L,n64_edge_W,n64_edge_drop],center=true);
}

module usbc_keepout() {
    color([0.7,0.7,0.7,0.9])
        translate([L/2-3,0,usbc_z-H/2])
            rotate([0,90,0]) cube([usbc_cut_H+2,usbc_cut_W-1,8],center=true);
}

module assembled() {
    color([0.18,0.20,0.24]) upper_shell();
    color([0.12,0.14,0.17]) lower_shell();
    if (show_keepouts) {
        pcb_keepout();
        snes_connector_keepout();
        n64_edge_keepout();
        usbc_keepout();
    }
}

module exploded() {
    translate([0,0,4]) upper_shell();
    translate([0,0,-4]) lower_shell();
    if (show_keepouts) {
        pcb_keepout();
        snes_connector_keepout();
        n64_edge_keepout();
        usbc_keepout();
    }
}

if (view_mode == 1) exploded();
else assembled();
