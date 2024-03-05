import React from 'react';
import AppBar from '@mui/material/AppBar'
import Typography from '@mui/material/Typography';
import Toolbar from '@mui/material/Toolbar';
import RomLogo from '../../assets/rom.png'
import GoogleLogo from '../../assets/maps_platform.png'

const TopAppBar = () => {
    return (
        <>
            <AppBar position='static' sx={{ backgroundColor: 'white', color: 'black'}}>
                <Toolbar sx={{ justifyContent: 'space-between', padding: '5px' }}> 
                    <img src={RomLogo} alt='rom-logo' style={{ height: '50px' }}/>
                    <div style={{ textAlign: 'right' }}>
                    <Typography variant="subtitle1" component="div" sx={{color: 'gray', fontSize: '12px'}}>Powered by</Typography>
                    <img src={GoogleLogo} alt='google-logo' style={{ width: '170px' }}/>
                    </div>
                </Toolbar>
            </AppBar>
        </>
    );
}

export default TopAppBar;
